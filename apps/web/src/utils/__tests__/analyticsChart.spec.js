/**
 * 看板图表数据整形的测试。
 *
 * 核心是钉住一条规则：**当天没有记录时，情绪评分必须是 null，不能是 0。**
 * 后端返回 0，但 1~10 量表里没有 0 这个分 —— 画出来会像「全员情绪跌到谷底」。
 */
import { describe, it, expect } from 'vitest'
import { toMoodSeries, toCountSeries, countDaysWithData } from '../analyticsChart'

/** 真实接口返回的样子：无记录的天 avgMoodScore 是 0、recordCount 也是 0 */
const REAL_DATA = [
    { date: '2026-09-26', avgMoodScore: 0, recordCount: 0 },
    { date: '2026-09-27', avgMoodScore: 0, recordCount: 0 },
    { date: '2026-09-28', avgMoodScore: 0, recordCount: 0 },
    { date: '2026-09-29', avgMoodScore: 0, recordCount: 0 },
    { date: '2026-09-30', avgMoodScore: 7.7, recordCount: 3 },
    { date: '2026-10-01', avgMoodScore: 5.0, recordCount: 4 },
    { date: '2026-10-02', avgMoodScore: 7.0, recordCount: 1 }
]

describe('toMoodSeries', () => {
    it('无记录的天置为 null，而不是照抄后端的 0', () => {
        const series = toMoodSeries(REAL_DATA)
        expect(series.slice(0, 4)).toEqual([null, null, null, null])
        expect(series.slice(4)).toEqual([7.7, 5.0, 7.0])
    })

    it('有记录但分数恰好是 0 时保留 0（不误判）', () => {
        // 边界：recordCount > 0 说明确实有记录，此时 0 是数据本身，要如实画
        const series = toMoodSeries([{ date: 'x', avgMoodScore: 0, recordCount: 1 }])
        expect(series).toEqual([0])
    })

    it('记录数量为 0 但分数非 0（脏数据）也置 null', () => {
        const series = toMoodSeries([{ date: 'x', avgMoodScore: 6, recordCount: 0 }])
        expect(series).toEqual([null])
    })

    it('空输入 / undefined 不炸', () => {
        expect(toMoodSeries([])).toEqual([])
        expect(toMoodSeries()).toEqual([])
        expect(toMoodSeries(undefined)).toEqual([])
    })

    it('缺字段的记录退化为 null', () => {
        expect(toMoodSeries([{ date: 'x' }])).toEqual([null])
        expect(toMoodSeries([{ date: 'x', recordCount: 2 }])).toEqual([null])
    })

    it('字符串数字也能处理（localStorage / JSON 反序列化的常见情况）', () => {
        const series = toMoodSeries([{ date: 'x', avgMoodScore: '6.5', recordCount: '2' }])
        expect(series).toEqual([6.5])
    })
})

describe('toCountSeries', () => {
    it('无记录的天保留 0 —— 那天确实记录了 0 条', () => {
        expect(toCountSeries(REAL_DATA)).toEqual([0, 0, 0, 0, 3, 4, 1])
    })

    it('空输入不炸', () => {
        expect(toCountSeries()).toEqual([])
    })
})

describe('countDaysWithData', () => {
    it('数出真正有记录的天数', () => {
        expect(countDaysWithData(REAL_DATA)).toBe(3)
    })

    it('空数据返回 0', () => {
        expect(countDaysWithData([])).toBe(0)
        expect(countDaysWithData()).toBe(0)
    })
})
