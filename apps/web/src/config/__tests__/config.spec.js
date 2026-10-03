import { describe, it, expect, vi, afterEach } from 'vitest'

/**
 * resolveFileUrl 曾经把服务器地址硬编码在代码里（159.75.169.224），
 * 换环境就得改代码。这里锁住三条契约：空值兜底、绝对地址透传、相对地址拼接。
 */
describe('resolveFileUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  async function load() {
    vi.resetModules()
    return import('../index.js')
  }

  it('空值返回空串', async () => {
    const { resolveFileUrl } = await load()
    expect(resolveFileUrl('')).toBe('')
    expect(resolveFileUrl(null)).toBe('')
    expect(resolveFileUrl(undefined)).toBe('')
  })

  it('已是 http(s) 绝对地址则原样返回，不重复拼接', async () => {
    vi.stubEnv('VITE_FILE_BASE_URL', 'https://cdn.example.com')
    const { resolveFileUrl } = await load()
    expect(resolveFileUrl('https://other.com/a.png')).toBe('https://other.com/a.png')
  })

  it('base 末尾有斜杠时不会拼出双斜杠', async () => {
    vi.stubEnv('VITE_FILE_BASE_URL', 'https://cdn.example.com/')
    const { resolveFileUrl } = await load()
    expect(resolveFileUrl('/files/a.png')).toBe('https://cdn.example.com/files/a.png')
  })

  it('path 缺前导斜杠时会自动补上', async () => {
    vi.stubEnv('VITE_FILE_BASE_URL', 'https://cdn.example.com')
    const { resolveFileUrl } = await load()
    expect(resolveFileUrl('files/a.png')).toBe('https://cdn.example.com/files/a.png')
  })

  it('未配置 base 时回退到同源', async () => {
    vi.stubEnv('VITE_FILE_BASE_URL', '')
    const { resolveFileUrl } = await load()
    expect(resolveFileUrl('/files/a.png')).toBe(`${window.location.origin}/files/a.png`)
  })
})

describe('apiBaseUrl / tokenPrefix 默认值', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('未配置时给出可用默认值', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '')
    vi.stubEnv('VITE_TOKEN_PREFIX', '')
    vi.resetModules()
    const { apiBaseUrl, tokenPrefix } = await import('../index.js')
    expect(apiBaseUrl).toBe('/api')
    expect(tokenPrefix).toBe('Bearer ')
  })
})
