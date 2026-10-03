<template>
  <div class="markdown-content" :class="{ 'ai-markdown': isAiMessage }">
    <div v-html="renderedContent"></div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { sanitizeHtml } from '@/utils/sanitize'

const props = defineProps({
  content: {
    type: String,
    required: true
  },
  isAiMessage: {
    type: Boolean,
    default: false
  }
})

/** 链接协议白名单：javascript: / data: 一律降级为 # */
const isSafeUrl = (url) => /^(https?:\/\/|mailto:|tel:|\/|\.\/|#)/i.test((url || '').trim())

const escapeHtml = (text) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

// 简单的Markdown渲染器
const renderedContent = computed(() => {
  let html = props.content || ''

  // 1) 先整体转义，确保内容里的原始标签不会变成结构
  html = escapeHtml(html)

  // 2) 处理代码块（```）
  html = html.replace(/```(\w+)?\n([\s\S]*?)\n```/g, (match, lang, code) => {
    return `<pre class="code-block"><code class="language-${lang || 'text'}">${code.trim()}</code></pre>`
  })

  // 3) 行内代码（`）
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')

  // 4) 粗体 / 斜体
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>')

  // 5) 标题
  html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>')

  // 6) 链接（协议白名单，挡掉 javascript: 伪协议）
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, text, url) => {
    const href = isSafeUrl(url) ? url.trim() : '#'
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`
  })

  // 7) 列表
  html = html.replace(/^- (.*)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
  html = html.replace(/^\d+\. (.*)$/gm, '<li>$1</li>')

  // 8) 引用 / 分割线 / 换行
  html = html.replace(/^> (.*)$/gm, '<blockquote>$1</blockquote>')
  html = html.replace(/^---$/gm, '<hr>')
  html = html.replace(/\n/g, '<br>')
  html = html.replace(/<br><br>/g, '<br>')

  // 9) 最后统一走白名单清洗：移除 on* 事件、非法标签与危险属性
  return sanitizeHtml(html)
})
</script>

<style scoped>
.markdown-content {
  line-height: 1.6;
  color: inherit;
}

.markdown-content h1,
.markdown-content h2,
.markdown-content h3 {
  margin: 1em 0 0.5em 0;
  font-weight: 600;
  line-height: 1.3;
}

.markdown-content h1 {
  font-size: 1.5em;
  border-bottom: 2px solid var(--nd-border);
  padding-bottom: 0.3em;
}

.markdown-content h2 {
  font-size: 1.3em;
  color: #374151;
}

.markdown-content h3 {
  font-size: 1.1em;
  color: #4b5563;
}

.markdown-content p {
  margin: 0.5em 0;
}

.markdown-content ul,
.markdown-content ol {
  margin: 0.5em 0;
  padding-left: 1.5em;
}

.markdown-content li {
  margin: 0.3em 0;
}

.markdown-content blockquote {
  border-left: 4px solid #d1d5db;
  padding-left: 1em;
  margin: 1em 0;
  color: #6b7280;
  font-style: italic;
  background: var(--nd-surface-soft);
  border-radius: 0 0.5em 0.5em 0;
  padding: 0.5em 1em;
}

.ai-markdown blockquote {
  border-left-color: #3b82f6;
  background: #eff6ff;
}

.markdown-content hr {
  border: none;
  border-top: 2px solid var(--nd-border);
  margin: 1.5em 0;
}

.markdown-content code.inline-code {
  background: #f3f4f6;
  padding: 0.2em 0.4em;
  border-radius: 0.25em;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.85em;
  color: #e11d48;
}

.ai-markdown code.inline-code {
  background: #dbeafe;
  color: var(--nd-primary-600);
}

.markdown-content pre.code-block {
  background: #1f2937;
  color: var(--nd-surface-soft);
  padding: 1em;
  border-radius: 0.5em;
  overflow-x: auto;
  margin: 1em 0;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.85em;
  line-height: 1.4;
}

.markdown-content pre.code-block code {
  background: none;
  padding: 0;
  color: inherit;
}

.markdown-content a {
  color: #3b82f6;
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color 0.2s ease;
}

.markdown-content a:hover {
  border-bottom-color: #3b82f6;
}

.ai-markdown a {
  color: var(--nd-primary-600);
}

.ai-markdown a:hover {
  border-bottom-color: var(--nd-primary-600);
}

.markdown-content strong {
  font-weight: 600;
  color: #374151;
}

.ai-markdown strong {
  color: var(--nd-primary-600);
}

.markdown-content em {
  font-style: italic;
  color: #6b7280;
}
</style>
