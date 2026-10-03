/**
 * 日记页危机反馈的静态守卫。
 *
 * 三条危机触发路径（对话 / 量表 / 日记）都必须给用户当场看到求助资源。
 * 对话靠 SSE 的 crisis 事件、量表靠 selfHarmRisk 的红色 alert —— 这两个
 * 有各自测试盯着；日记这条曾长期缺失（用户写出高危内容，后端记了工单、
 * 老师会收到通知，当事人自己什么都看不到），修复后用静态断言钉住，
 * 防止将来重构时又被无声删掉。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

const stripComments = (src) =>
    src
        .replace(/<!--[\s\S]*?-->/g, '')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/^[ \t]*\/\/.*$/gm, '')

const DIARY = stripComments(fs.readFileSync(path.resolve(here, '..', 'views/emotionDiary.vue'), 'utf-8'))

describe('日记页危机反馈', () => {
    it('保存后必须根据 crisisLevel 展示求助卡', () => {
        expect(DIARY).toContain('crisisLevel')
        expect(DIARY).toContain('crisisCard')
        expect(DIARY).toContain('updateCrisisCard')
    })

    it('求助卡必须给出真实热线（12356）', () => {
        expect(DIARY).toContain('CRISIS_HELPLINES')
        expect(DIARY).toContain('crisisResources')
    })

    it('模型层风险 >= 2 时同样要展示（与后端 LLM_RISK_THRESHOLD 对齐）', () => {
        expect(DIARY).toMatch(/llmLevel\s*>=\s*2/)
    })
})
