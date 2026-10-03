/**
 * 极简 HTML 白名单清洗器（零依赖，替代 DOMPurify）。
 *
 * 背景：AI 回复、富文本文章都会经 v-html 渲染，而 token 存在 localStorage —— 一旦
 * 注入成功就等于账号接管。所有 v-html 内容必须先过这里。
 *
 * 策略：白名单标签 + 白名单属性 + 链接协议白名单 + 移除所有 on* 事件属性。
 */

/** 允许保留的标签；不在表内的标签会被"拆掉外壳、保留文字" */
const ALLOWED_TAGS = new Set([
  'p', 'br', 'hr', 'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins', 'sub', 'sup',
  'code', 'pre', 'blockquote', 'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'a', 'span', 'div',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
  'img'
])

/** 各标签允许保留的属性 */
const ALLOWED_ATTRS = {
  a: ['href', 'title', 'target', 'rel'],
  img: ['src', 'alt', 'title', 'width', 'height'],
  td: ['colspan', 'rowspan'],
  th: ['colspan', 'rowspan'],
  '*': ['class']
}

/** 只放行这些协议的链接与图片地址，挡掉 javascript: / data: / vbscript: 等 */
const SAFE_URL = /^(https?:\/\/|mailto:|tel:|\/|\.\/|\.\.\/|#)/i

function isSafeUrl(value) {
  if (!value) return false
  // 去掉空白与不可见字符后再判断，防 "java\nscript:" 之类的绕过。
  // 这里的控制字符是刻意匹配的，正是要拦的对象，故关闭该规则。
  // eslint-disable-next-line no-control-regex
  const cleaned = value.replace(/[\u0000-\u0020]/g, '').toLowerCase()
  if (cleaned.startsWith('javascript:') || cleaned.startsWith('data:') || cleaned.startsWith('vbscript:')) {
    return false
  }
  return SAFE_URL.test(value.trim())
}

function cleanNode(node, doc) {
  const children = Array.from(node.childNodes)
  for (const child of children) {
    // 注释直接丢弃
    if (child.nodeType === 8) {
      child.remove()
      continue
    }
    if (child.nodeType !== 1) {
      continue // 文本节点保留
    }

    const tag = child.tagName.toLowerCase()

    // 不在白名单：拆掉标签本身，保留里面的文字（再递归清洗子节点）
    if (!ALLOWED_TAGS.has(tag)) {
      const fragment = doc.createDocumentFragment()
      while (child.firstChild) {
        fragment.appendChild(child.firstChild)
      }
      child.replaceWith(fragment)
      cleanNode(node, doc)
      return
    }

    // 属性白名单
    const allowed = ALLOWED_ATTRS[tag] || []
    const common = ALLOWED_ATTRS['*'] || []
    for (const attr of Array.from(child.attributes)) {
      const name = attr.name.toLowerCase()
      if (name.startsWith('on')) {
        child.removeAttribute(attr.name)
        continue
      }
      if (!allowed.includes(name) && !common.includes(name)) {
        child.removeAttribute(attr.name)
        continue
      }
      if ((name === 'href' || name === 'src') && !isSafeUrl(attr.value)) {
        child.removeAttribute(attr.name)
      }
    }

    if (tag === 'a') {
      child.setAttribute('rel', 'noopener noreferrer')
      if (!child.getAttribute('target')) {
        child.setAttribute('target', '_blank')
      }
    }

    cleanNode(child, doc)
  }
}

/**
 * 清洗 HTML 片段，返回可安全交给 v-html 的字符串。
 * @param {string} dirty 待清洗的 HTML
 * @returns {string} 清洗后的 HTML
 */
export function sanitizeHtml(dirty) {
  if (!dirty) return ''
  if (typeof dirty !== 'string') return ''

  const parser = new DOMParser()
  // 用 text/html 解析得到的文档是惰性的：里面的 <script> 不会执行
  const doc = parser.parseFromString('<div id="__sanitize_root__">' + dirty + '</div>', 'text/html')
  const root = doc.getElementById('__sanitize_root__')
  if (!root) return ''

  cleanNode(root, doc)
  return root.innerHTML
}

/** 纯文本转义（用于不需要任何标签的场景） */
export function escapeHtml(text) {
  if (text == null) return ''
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export default sanitizeHtml
