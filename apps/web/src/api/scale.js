import service from '@/utils/request'

/**
 * 标准化量表接口（PHQ-9 / GAD-7）。
 *
 * 题目与选项都由后端下发，前端不内置任何题目文案 ——
 * 量表措辞一旦两端各写一份，改了一边就会导致结果不可比。
 */

/** 取题目与选项，code 为 PHQ9 或 GAD7 */
export const getScaleQuestions = (code = 'PHQ9') =>
  service.get('/scale/questions', { params: { code } })

/** 提交答案并计分。answers 是 0-3 的整数数组 */
export const submitScale = (scaleCode, answers) =>
  service.post('/scale/submit', { scaleCode, answers })

/** 我的量表历史（可只取某一种） */
export const getMyScaleHistory = (code) =>
  service.get('/scale/my', { params: code ? { code } : {} })

/** 最近一次结果，没做过返回 null */
export const getMyScaleLatest = (code = 'PHQ9') =>
  service.get('/scale/my/latest', { params: { code } })

/** 趋势（按日期升序，供折线图） */
export const getScaleTrend = (code) =>
  service.get('/scale/trend', { params: code ? { code } : {} })
