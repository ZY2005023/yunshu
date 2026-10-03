/**
 * 会话情绪接口返回值 → 情绪花园状态的归一化。
 *
 * 为什么要单独抽出来（与 moodStats.js / analyticsChart.js 同一套理由）：
 *  1. 这里的字段兜底全是边界情况，值得单独测；
 *  2. 内联在 consultation.vue 里的话，测试必须挂载整个页面 ——
 *     那要连带 mock element-plus、echarts 和 fetch-event-source，成本高且脆。
 *
 * 修复过的真实事故（2026-10-02 排查）：
 *   loadSessionEmotion 原来把接口返回**原样**赋给 currentEmotion，
 *   而 /session/{id}/emotion 返回的是 { sessionId, emotionAnalysis: null }
 *   （emotionAnalysis 在 last_emotion_analysis 落地前恒为 null）。
 *   模板里 `currentEmotion.improvementSuggestions.length > 0` 会在新对象上
 *   取 undefined.length → 渲染中断 —— 第一条 AI 回复完成后页面就「冻住」。
 */

/**
 * 情绪花园的兜底状态。接口没给分析（或还没分析）时必须完整可用，
 * 任何一个字段缺失都可能让模板在取子属性时抛错。
 */
export const DEFAULT_EMOTION_STATE = Object.freeze({
    primaryEmotion: '中性',
    emotionScore: 50,
    isNegative: false,
    riskLevel: 0,
    suggestion: '情绪状态平稳',
    improvementSuggestions: []
})

/**
 * 把接口返回归一化成情绪花园可用状态。
 *
 * 规则：
 *  · 没有 emotionAnalysis（null / 非 object）→ 整体回到兜底状态。
 *    切换会话时必须复位，不能带着上一个会话的风险等级走。
 *  · 有 emotionAnalysis → 在兜底之上合并，缺的字段用兜底补齐
 *    （AI 分析不返回 emotionScore / isNegative，这两项目前只有兜底值）。
 *  · improvementSuggestions 必须是数组 —— 模板要取它的 length。
 *
 * @param {{sessionId?: string, emotionAnalysis?: object|null}|null|undefined} res 接口返回
 * @param {object} [fallback] 兜底状态，测试可注入
 * @returns {object} 可直接赋给 currentEmotion 的完整状态
 */
export function normalizeEmotionState(res, fallback = DEFAULT_EMOTION_STATE) {
    const analysis = res && typeof res === 'object' ? res.emotionAnalysis : null
    if (!analysis || typeof analysis !== 'object' || Array.isArray(analysis)) {
        return { ...fallback }
    }

    const suggestions = Array.isArray(analysis.improvementSuggestions)
        ? analysis.improvementSuggestions
        : []

    return { ...fallback, ...analysis, improvementSuggestions: suggestions }
}
