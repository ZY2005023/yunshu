/**
 * sessionEmotion.js 的单元测试。
 *
 * 背景：consultation.vue 的 loadSessionEmotion 曾经把接口返回**原样**
 * 赋给情绪花园状态 —— 接口形状是 { sessionId, emotionAnalysis: null }，
 * 模板取 currentEmotion.improvementSuggestions.length 直接抛 TypeError，
 * 第一条 AI 回复完成后整个面板「冻住」。归一化逻辑抽出后在这里钉死。
 */
import { describe, it, expect } from 'vitest'
import { DEFAULT_EMOTION_STATE, normalizeEmotionState } from '@/utils/sessionEmotion'

describe('normalizeEmotionState', () => {
    it('接口返回为 null / undefined 时回退到完整兜底状态', () => {
        for (const res of [null, undefined]) {
            const state = normalizeEmotionState(res)
            expect(state).toEqual({ ...DEFAULT_EMOTION_STATE })
            // 模板要在这个字段上取 length，绝不能是 undefined
            expect(Array.isArray(state.improvementSuggestions)).toBe(true)
        }
    })

    it('emotionAnalysis 为 null（分析未落地）时同样回退兜底', () => {
        const state = normalizeEmotionState({ sessionId: 'session_1', emotionAnalysis: null })
        expect(state).toEqual({ ...DEFAULT_EMOTION_STATE })
        expect(state.riskLevel).toBe(0)
    })

    it('切换会话必须复位 —— 不能带着上一个会话的风险等级走', () => {
        // 先看过一个高危会话
        const risky = normalizeEmotionState({
            sessionId: 'session_1',
            emotionAnalysis: { riskLevel: 3, primaryEmotion: '绝望' }
        })
        expect(risky.riskLevel).toBe(3)

        // 再点开一个还没有分析结果的会话 → 必须回到中性，而不是残留 3
        const next = normalizeEmotionState({ sessionId: 'session_2', emotionAnalysis: null })
        expect(next.riskLevel).toBe(0)
        expect(next.primaryEmotion).toBe('中性')
    })

    it('有分析结果时在兜底之上合并，缺的字段由兜底补齐', () => {
        const state = normalizeEmotionState({
            sessionId: 'session_1',
            emotionAnalysis: {
                primaryEmotion: '焦虑',
                riskLevel: 2,
                suggestion: '试试 4-7-8 呼吸法',
                improvementSuggestions: ['写下担忧', '散步十分钟']
            }
        })
        expect(state.primaryEmotion).toBe('焦虑')
        expect(state.riskLevel).toBe(2)
        expect(state.suggestion).toBe('试试 4-7-8 呼吸法')
        expect(state.improvementSuggestions).toEqual(['写下担忧', '散步十分钟'])
        // AI 分析不返回 emotionScore / isNegative —— 用兜底值，绝不能是 undefined
        expect(state.emotionScore).toBe(DEFAULT_EMOTION_STATE.emotionScore)
        expect(state.isNegative).toBe(DEFAULT_EMOTION_STATE.isNegative)
    })

    it('improvementSuggestions 缺失或不是数组时强制归一为数组', () => {
        const missing = normalizeEmotionState({
            emotionAnalysis: { primaryEmotion: '平静' }
        })
        expect(missing.improvementSuggestions).toEqual([])

        const notArray = normalizeEmotionState({
            emotionAnalysis: { primaryEmotion: '平静', improvementSuggestions: '早睡' }
        })
        expect(notArray.improvementSuggestions).toEqual([])
    })

    it('emotionAnalysis 是数组等异常形状时按「无分析」处理，不抛错', () => {
        const state = normalizeEmotionState({ sessionId: 's', emotionAnalysis: [1, 2, 3] })
        expect(state).toEqual({ ...DEFAULT_EMOTION_STATE })
    })

    it('兜底状态本身必须是完整可渲染的', () => {
        expect(Array.isArray(DEFAULT_EMOTION_STATE.improvementSuggestions)).toBe(true)
        expect(typeof DEFAULT_EMOTION_STATE.riskLevel).toBe('number')
        expect(typeof DEFAULT_EMOTION_STATE.suggestion).toBe('string')
    })
})
