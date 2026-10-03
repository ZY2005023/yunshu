/**
 * 对话页流式链路的静态守卫。
 *
 * 两个修过的真实事故（都是"构建通过、单测通过，只有真跑起来才发现"型）：
 *  1. 流式进行中点击其他会话不掐断旧流 → onmessage 往新会话的消息列表
 *     追加内容，AI 回复串台、输入框卡死在禁用态 —— handleSessionClick
 *     必须先 abortStream()；
 *  2. loadSessionEmotion 把 { sessionId, emotionAnalysis } 原样赋给
 *     currentEmotion → 模板取 undefined.length 渲染中断 —— 必须经过
 *     normalizeEmotionState 归一化，不许直接赋值。
 *
 * 用静态断言的原因与 copy-promises.spec.js 相同：挂载整个 consultation.vue
 * 要 mock element-plus、echarts、fetch-event-source 和 SSE 时序，成本高且脆；
 * 这两条约束的本质是「代码形状」，静态断言即可钉住。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

/** 剥掉注释再校验 —— 这些文件的注释里正是在**讨论**那些错误写法 */
const stripComments = (src) =>
    src
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/^[ \t]*\/\/.*$/gm, '')

const CONSULTATION = stripComments(
    fs.readFileSync(path.resolve(here, '..', 'views/consultation.vue'), 'utf-8')
)

const extractFunction = (name) => {
    const start = CONSULTATION.indexOf(`const ${name} =`)
    if (start < 0) throw new Error(`找不到函数 ${name}`)
    const next = CONSULTATION.indexOf('\nconst ', start + 1)
    return CONSULTATION.slice(start, next > 0 ? next : undefined)
}

describe('consultation.vue 流式链路守卫', () => {
    it('handleSessionClick 必须先掐断进行中的流再切换', () => {
        const fn = extractFunction('handleSessionClick')
        const abortPos = fn.indexOf('abortStream()')
        const detailPos = fn.indexOf('getSessionDetail(')
        expect(abortPos).toBeGreaterThan(-1)
        expect(detailPos).toBeGreaterThan(-1)
        expect(abortPos).toBeLessThan(detailPos)
    })

    it('loadSessionEmotion 不得把接口返回原样赋给 currentEmotion', () => {
        const fn = extractFunction('loadSessionEmotion')
        // 必须经归一化
        expect(fn).toContain('normalizeEmotionState(')
        // 不允许直接赋原始响应（历史事故写法：currentEmotion.value = res）
        expect(fn).not.toMatch(/currentEmotion\.value\s*=\s*res\b/)
    })

    it('onerror 对主动掐断的流必须静默处理，不许弹「AI回复失败」', () => {
        const onerrorPos = CONSULTATION.indexOf('onerror:')
        const onclosePos = CONSULTATION.indexOf('onclose:')
        expect(onerrorPos).toBeGreaterThan(-1)
        const fn = CONSULTATION.slice(onerrorPos, onclosePos > 0 ? onclosePos : undefined)
        expect(fn).toContain('streamAbortedLocally')
    })
})
