import { describe, it, expect } from 'vitest'
import { sanitizeHtml, escapeHtml } from '../sanitize.js'

/**
 * 这些用例是回归护栏，不是文档。
 * 每一条都对应一种真实的绕过手法 —— 一旦有人为了"方便"放宽白名单，
 * 这里必须先红，而不是等 token 被偷走之后才发现。
 */

describe('escapeHtml', () => {
  it('转义全部五个危险字符', () => {
    expect(escapeHtml(`<a href="x" title='y'>&`)).toBe(
      '&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;'
    )
  })

  it('null / undefined 返回空串', () => {
    expect(escapeHtml(null)).toBe('')
    expect(escapeHtml(undefined)).toBe('')
  })

  it('非字符串入参也能处理', () => {
    expect(escapeHtml(123)).toBe('123')
  })
})

describe('sanitizeHtml 基本行为', () => {
  it('空值返回空串', () => {
    expect(sanitizeHtml('')).toBe('')
    expect(sanitizeHtml(null)).toBe('')
    expect(sanitizeHtml(undefined)).toBe('')
  })

  it('非字符串入参不会抛异常', () => {
    expect(sanitizeHtml(123)).toBe('')
    expect(sanitizeHtml({ a: 1 })).toBe('')
  })

  it('保留白名单标签', () => {
    expect(sanitizeHtml('<p>你好</p>')).toBe('<p>你好</p>')
  })

  it('非白名单标签拆掉外壳但保留文字', () => {
    expect(sanitizeHtml('<marquee>滚动</marquee>')).toBe('滚动')
  })

  it('注释被丢弃', () => {
    expect(sanitizeHtml('<p>a</p><!-- 恶意注释 -->')).toBe('<p>a</p>')
  })
})

describe('sanitizeHtml 拦截脚本注入', () => {
  it('script 标签被拆壳，内容变成惰性文本', () => {
    const out = sanitizeHtml('<script>alert(1)</script>')
    expect(out).not.toContain('<script')
    expect(out).not.toContain('</script')
    expect(out).toContain('alert(1)')
  })

  it('script 带属性也拦得住', () => {
    const out = sanitizeHtml('<script type="text/javascript" src="https://evil.com/x.js"></script>')
    expect(out).not.toContain('<script')
    expect(out).not.toContain('evil.com/x.js"')
  })

  it('img 的 onerror 被移除', () => {
    expect(sanitizeHtml('<img src="/a.png" onerror="alert(1)">')).not.toContain('onerror')
  })

  it('img 无引号形式的 onerror 同样被移除', () => {
    expect(sanitizeHtml('<img src=x onerror=alert(1)>')).not.toContain('onerror')
  })

  it('白名单标签上的 onclick 被移除', () => {
    expect(sanitizeHtml('<p onclick="alert(1)">x</p>')).not.toContain('onclick')
  })

  it('onload / onmouseover 等一切 on* 属性都被移除', () => {
    const out = sanitizeHtml('<div onload="x" onmouseover="y" onfocus="z">h</div>')
    expect(out).not.toContain('onload')
    expect(out).not.toContain('onmouseover')
    expect(out).not.toContain('onfocus')
  })

  it('svg onload 组合攻击被拦下', () => {
    const out = sanitizeHtml('<svg onload="alert(1)"><circle r="1"/></svg>')
    expect(out).not.toContain('onload')
    expect(out).not.toContain('<svg')
  })

  it('iframe 被拆壳', () => {
    expect(sanitizeHtml('<iframe src="https://evil.com"></iframe>')).not.toContain('<iframe')
  })

  it('form / input 被拆壳', () => {
    const out = sanitizeHtml('<form action="https://evil.com"><input name="a"></form>')
    expect(out).not.toContain('<form')
    expect(out).not.toContain('<input')
  })
})

describe('sanitizeHtml 拦截危险协议', () => {
  it('javascript: 链接被摘掉 href', () => {
    const out = sanitizeHtml('<a href="javascript:alert(1)">点我</a>')
    expect(out).not.toContain('javascript:')
    expect(out).toContain('点我')
  })

  it('大小写变形的 JavaScript: 也被拦下', () => {
    expect(sanitizeHtml('<a href="JaVaScRiPt:alert(1)">x</a>')).not.toContain('href')
  })

  it('用制表符/换行拆词的绕过被拦下', () => {
    expect(sanitizeHtml('<a href="java&#9;script:alert(1)">x</a>')).not.toContain('script:')
    expect(sanitizeHtml('<a href="java&#10;script:alert(1)">x</a>')).not.toContain('script:')
  })

  it('data: 协议的 img 被摘掉 src', () => {
    expect(sanitizeHtml('<img src="data:image/svg+xml;base64,PHN2Zz4=">')).not.toContain('data:')
  })

  it('vbscript: 协议被拦下', () => {
    expect(sanitizeHtml('<a href="vbscript:msgbox(1)">x</a>')).not.toContain('vbscript')
  })

  it('style 属性（可作为 css 注入入口）被移除', () => {
    expect(sanitizeHtml('<p style="color:red">x</p>')).not.toContain('style=')
  })
})

describe('sanitizeHtml 不误伤正常内容', () => {
  it('https 链接保留，并补上 rel 与 target', () => {
    const out = sanitizeHtml('<a href="https://example.com">官网</a>')
    expect(out).toContain('href="https://example.com"')
    expect(out).toContain('rel="noopener noreferrer"')
    expect(out).toContain('target="_blank"')
  })

  it('站内相对链接保留', () => {
    expect(sanitizeHtml('<a href="/docs/a">x</a>')).toContain('href="/docs/a"')
  })

  it('锚点链接保留', () => {
    expect(sanitizeHtml('<a href="#top">x</a>')).toContain('href="#top"')
  })

  it('mailto / tel 保留', () => {
    expect(sanitizeHtml('<a href="mailto:a@b.com">x</a>')).toContain('mailto:a@b.com')
    expect(sanitizeHtml('<a href="tel:12356">x</a>')).toContain('tel:12356')
  })

  it('作者指定的 target 不被覆盖', () => {
    expect(sanitizeHtml('<a href="https://a.com" target="_self">x</a>')).toContain(
      'target="_self"'
    )
  })

  it('class 属性在任意白名单标签上保留', () => {
    expect(sanitizeHtml('<p class="tip">x</p>')).toContain('class="tip"')
  })

  it('表格的 colspan / rowspan 保留', () => {
    const out = sanitizeHtml('<table><tr><td colspan="2">x</td></tr></table>')
    expect(out).toContain('colspan="2"')
  })

  it('相对路径图片与 alt 保留', () => {
    const out = sanitizeHtml('<img src="/files/a.png" alt="封面">')
    expect(out).toContain('src="/files/a.png"')
    expect(out).toContain('alt="封面"')
  })

  it('代码块与列表结构保留', () => {
    const out = sanitizeHtml('<pre><code>a&lt;b</code></pre><ul><li>x</li></ul>')
    expect(out).toContain('<pre>')
    expect(out).toContain('<code>')
    expect(out).toContain('<ul>')
    expect(out).toContain('<li>')
  })
})
