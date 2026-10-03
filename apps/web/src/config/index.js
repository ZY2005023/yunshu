/**
 * 前端运行期配置。
 *
 * 原来这里硬编码了 `http://159.75.169.224:1235`——换环境就得改代码。
 * 现在优先读 .env 里的 VITE_FILE_BASE_URL；没配时回退到"同源"，
 * 配合 vite 的 /api 代理与后端 /files 静态映射即可正常工作。
 */
export const fileBaseUrl = import.meta.env.VITE_FILE_BASE_URL || window.location.origin

/** 接口基础地址（与 request.js 保持一致，供 SSE 等非 axios 场景使用） */
export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

/** 鉴权请求头前缀 */
export const tokenPrefix = import.meta.env.VITE_TOKEN_PREFIX || 'Bearer '

/** 拼装可访问的文件地址：后端返回的 filePath 形如 /files/xxx/yyy.png */
export function resolveFileUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path)) return path
  return fileBaseUrl.replace(/\/$/, '') + (path.startsWith('/') ? path : '/' + path)
}
