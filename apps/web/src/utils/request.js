import axios from 'axios'
import { ElMessage } from 'element-plus'

/**
 * 统一请求层。
 *
 * 改造点：
 *  1. baseURL 走环境变量，不再硬编码；
 *  2. 普通接口 15s 超时，AI 相关接口单独 120s（原来统一 5s，AI 请求必超时）；
 *  3. 请求头统一 Authorization: Bearer（后端已同步支持）；
 *  4. 401 时用 refresh token 静默续期并重放一次请求，失败才跳登录；
 *  5. 网络异常 / 业务错误统一提示，调用方不必再各自处理。
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'
const TOKEN_PREFIX = import.meta.env.VITE_TOKEN_PREFIX || 'Bearer '

const DEFAULT_TIMEOUT = 15000
/** AI 流式与长耗时接口的超时 */
const AI_TIMEOUT = 120000
const AI_URL_PREFIXES = ['/psychological-chat/', '/emotion-diary']

const service = axios.create({
  baseURL: BASE_URL,
  timeout: DEFAULT_TIMEOUT
})

/** 无需鉴权 / 不需要自动续期的接口 */
const isAuthFree = (url = '') =>
  url.includes('/user/login') || url.includes('/user/add') || url.includes('/user/refresh')

// ==================== 请求拦截 ====================
service.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = TOKEN_PREFIX + token
    }
    if (AI_URL_PREFIXES.some((p) => (config.url || '').includes(p))) {
      config.timeout = AI_TIMEOUT
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ==================== 令牌续期 ====================
/** 并发请求同时 401 时，只发起一次刷新 */
let refreshingPromise = null

async function requestNewToken() {
  const refreshToken = localStorage.getItem('refreshToken')
  if (!refreshToken) {
    throw new Error('没有可用的刷新令牌')
  }
  // 用裸 axios，避免再次进入本拦截器造成递归
  const res = await axios.post(`${BASE_URL}/user/refresh`, { refreshToken }, { timeout: DEFAULT_TIMEOUT })
  const body = res.data
  if (!body || body.code !== '200' || !body.data || !body.data.token) {
    throw new Error((body && body.msg) || '刷新令牌失败')
  }
  localStorage.setItem('token', body.data.token)
  if (body.data.refreshToken) {
    localStorage.setItem('refreshToken', body.data.refreshToken)
  }
  return body.data.token
}

/**
 * 静默续期（并发安全：同一时刻只有一次刷新在飞）。
 * 供两处使用：axios 401 拦截器、SSE 的 fetch-event-source（不走 axios 拦截器，
 * access token 过期时此前只会报「AI回复失败」，现在能先续期再重试）。
 */
export function refreshTokenSilently() {
  if (!refreshingPromise) {
    refreshingPromise = requestNewToken().finally(() => {
      refreshingPromise = null
    })
  }
  return refreshingPromise
}

/** 清登录态并跳登录页。SSE 续期失败时复用，与 axios 401 拦截行为保持一致。 */
export function clearAuthAndRedirect() {
  localStorage.removeItem('token')
  localStorage.removeItem('refreshToken')
  localStorage.removeItem('userInfo')
  const { pathname, search } = window.location
  if (!pathname.startsWith('/auth/login')) {
    window.location.href = `/auth/login?redirect=${encodeURIComponent(pathname + search)}`
  }
}

// ==================== 响应拦截 ====================
service.interceptors.response.use(
  (response) => {
    const { data } = response
    // 后端统一返回体：{ code, msg, data }
    if (data && data.code === '200') {
      return data.data
    }
    const msg = (data && data.msg) || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(new Error(msg))
  },
  async (error) => {
    const { response, config } = error || {}

    // 网络层异常（断网 / 超时 / 主动取消）
    if (!response) {
      if (error && error.code === 'ECONNABORTED') {
        ElMessage.error('请求超时，请稍后重试')
      } else if (error && error.code !== 'ERR_CANCELED') {
        ElMessage.error('网络异常，请检查网络后重试')
      }
      return Promise.reject(error)
    }

    const status = response.status
    const isRetried = config && config._retried

    // 访问令牌过期：先静默续期并重放一次
    if (status === 401 && config && !isRetried && !isAuthFree(config.url)) {
      config._retried = true
      try {
        if (!refreshingPromise) {
          refreshingPromise = requestNewToken().finally(() => {
            refreshingPromise = null
          })
        }
        const newToken = await refreshingPromise
        config.headers['Authorization'] = TOKEN_PREFIX + newToken
        return service(config)
      } catch (e) {
        clearAuthAndRedirect()
        return Promise.reject(e)
      }
    }

    if (status === 401) {
      ElMessage.error('登录状态已失效，请重新登录')
      clearAuthAndRedirect()
    } else if (status === 403) {
      ElMessage.error('没有权限执行该操作')
    } else {
      ElMessage.error((response.data && response.data.msg) || `请求失败（${status}）`)
    }
    return Promise.reject(error)
  }
)

export default service
