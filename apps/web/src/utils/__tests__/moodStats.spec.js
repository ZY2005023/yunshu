/**
 * 情绪日记派生逻辑的单元测试。
 *
 * 这些边界原本藏在组件的 computed 里没人验证过 ——
 * 尤其是「今天还没记录时连续天数是否会归零」和「月历首日偏移」，
 * 错了只会表现为 UI 上差一格或数字不对，很难被发现。
 */
import { describe, it, expect } from 'vitest'
import { dayjs } from 'element-plus'

import {
    moodLevel,
    buildDiaryMap,
    calcStreak,
    calcMonthStats,
    buildCalendar,
    groupByMonth,
    pickInitialMonth
} from '../moodStats'

const TODAY = dayjs('2026-10-03') // 周六

const d = (date, score, emotion) => ({
    id: date,
    diaryDate: date,
    moodScore: score,
    dominantEmotion: emotion
})

describe('moodLevel', () => {
    it.each([
        [null, 0],
        [undefined, 0],
        [0, 0],
        [1, 1],
        [2, 1],
        [3, 2],
        [4, 2],
        [5, 3],
        [6, 3],
        [7, 4],
        [8, 4],
        [9, 5],
        [10, 5]
    ])('分数 %s -> 档位 %s', (score, level) => {
        expect(moodLevel(score)).toBe(level)
    })

    it('低分档位不等于 0 —— 0 是「无记录」的专用值', () => {
        expect(moodLevel(1)).not.toBe(0)
    })
})

describe('buildDiaryMap', () => {
    it('按日期建索引', () => {
        const m = buildDiaryMap([d('2026-10-01', 6), d('2026-10-02', 8)])
        expect(m.size).toBe(2)
        expect(m.get('2026-10-02').moodScore).toBe(8)
    })

    it('跳过缺失日期的脏数据，不抛异常', () => {
        const m = buildDiaryMap([d('2026-10-01', 6), { id: 9 }, null, undefined])
        expect(m.size).toBe(1)
    })

    it('空输入返回空 Map', () => {
        expect(buildDiaryMap().size).toBe(0)
        expect(buildDiaryMap([]).size).toBe(0)
    })
})

describe('calcStreak', () => {
    const mapOf = (dates) => buildDiaryMap(dates.map((x) => d(x, 6)))

    it('今天、昨天、前天都有记录 -> 3', () => {
        expect(calcStreak(mapOf(['2026-10-03', '2026-10-02', '2026-10-01']), TODAY)).toBe(3)
    })

    it('今天还没记录，但昨天有 —— 不归零，从昨天起算', () => {
        // 这条很关键：一早打开就显示「连续 0 天」会让用户以为记录丢了
        expect(calcStreak(mapOf(['2026-10-02', '2026-10-01']), TODAY)).toBe(2)
    })

    it('今天和昨天都没记录 -> 0', () => {
        expect(calcStreak(mapOf(['2026-10-01']), TODAY)).toBe(0)
    })

    it('中间断档时只数最后一段连续', () => {
        // 10-03、10-02 连续；10-01 缺；09-30 有
        expect(calcStreak(mapOf(['2026-10-03', '2026-10-02', '2026-09-30']), TODAY)).toBe(2)
    })

    it('跨月连续也算', () => {
        // 今天(10-03)未记录 -> 从 10-02 起算，跨回 9 月仍是连续的 4 天
        expect(
            calcStreak(mapOf(['2026-10-02', '2026-10-01', '2026-09-30', '2026-09-29']), TODAY)
        ).toBe(4)
    })

    it('完全没有记录 -> 0', () => {
        expect(calcStreak(new Map(), TODAY)).toBe(0)
    })
})

describe('calcMonthStats', () => {
    it('统计当月记录数、平均分与最常见情绪', () => {
        const list = [
            d('2026-10-01', 6, '平静'),
            d('2026-10-02', 8, '开心'),
            d('2026-10-03', 4, '焦虑'),
            d('2026-09-30', 2, '悲伤') // 上个月，不该被统计
        ]
        const s = calcMonthStats(list, '2026-10')
        expect(s.days).toBe(3)
        expect(s.avg).toBe(6)
        expect(s.topEmotion).toBe('平静')
    })

    it('平均分保留一位小数', () => {
        const s = calcMonthStats([d('2026-10-01', 5), d('2026-10-02', 6), d('2026-10-03', 6)], '2026-10')
        expect(s.avg).toBe(5.7) // 17/3 = 5.666…
    })

    it('最常见情绪并列时取先出现的', () => {
        const s = calcMonthStats(
            [d('2026-10-01', 5, '焦虑'), d('2026-10-02', 5, '开心')],
            '2026-10'
        )
        expect(s.topEmotion).toBe('焦虑')
    })

    it('没有记录时返回中性值，不抛异常', () => {
        const s = calcMonthStats([], '2026-10')
        expect(s.days).toBe(0)
        expect(s.avg).toBe(0)
        expect(s.topEmotion).toBe(null)
    })

    it('缺分数的记录计入条数，但不拉低平均分', () => {
        const s = calcMonthStats([d('2026-10-01', 8), { id: 'x', diaryDate: '2026-10-02' }], '2026-10')
        expect(s.days).toBe(2)
        expect(s.avg).toBe(8)
    })
})

describe('buildCalendar', () => {
    it('格子数 = 首日偏移 + 当月天数', () => {
        // 2026-10-01 是周四 -> 前面补 4 个空位，10 月 31 天
        const cells = buildCalendar('2026-10')
        expect(cells.length).toBe(4 + 31)
        expect(cells.slice(0, 4).every((c) => c === null)).toBe(true)
        expect(cells[4].day).toBe(1)
        expect(cells[cells.length - 1].day).toBe(31)
    })

    it('首日正好是周日时没有空位', () => {
        // 2026-02-01 是周日
        const cells = buildCalendar('2026-02')
        expect(cells.length).toBe(28)
        expect(cells[0].day).toBe(1)
        expect(cells[0].key).toBe('2026-02-01')
    })

    it('闰年 2 月按 29 天', () => {
        const cells = buildCalendar('2024-02')
        expect(cells.filter(Boolean).length).toBe(29)
    })

    it('把已有记录绑定到对应日期', () => {
        const map = buildDiaryMap([d('2026-10-05', 9, '兴奋')])
        const cells = buildCalendar('2026-10', map)
        const hit = cells.find((c) => c && c.day === 5)
        expect(hit.diary.moodScore).toBe(9)

        const miss = cells.find((c) => c && c.day === 6)
        expect(miss.diary).toBe(null)
    })
})

describe('groupByMonth', () => {
    const list = [
        d('2026-10-03', 3, '焦虑'),
        d('2026-10-01', 8, '开心'),
        d('2026-09-28', 2, '疲惫')
    ]

    it('按月分组，保持原数组内的先后顺序', () => {
        const groups = groupByMonth(list)
        expect(groups.length).toBe(2)
        expect(groups[0].month).toBe('2026-10')
        expect(groups[0].items.length).toBe(2)
        expect(groups[0].label).toBe('2026 年 10 月')
        expect(groups[1].month).toBe('2026-09')
    })

    it('onlyLow 只保留情绪偏低的记录', () => {
        const groups = groupByMonth(list, { onlyLow: true })
        const all = groups.flatMap((g) => g.items)
        expect(all.length).toBe(2)
        expect(all.every((x) => x.moodScore <= 4)).toBe(true)
    })

    it('缺日期的记录归到「未标注日期」而不是被丢掉', () => {
        const groups = groupByMonth([{ id: 1, moodScore: 5 }])
        expect(groups[0].month).toBe('unknown')
        expect(groups[0].label).toBe('未标注日期')
    })

    it('空输入返回空数组', () => {
        expect(groupByMonth([])).toEqual([])
        expect(groupByMonth()).toEqual([])
    })
})

describe('pickInitialMonth', () => {
    it('当前月有记录 -> 停在当前月', () => {
        const list = [d('2026-10-02', 7), d('2025-11-11', 5)]
        expect(pickInitialMonth(list, TODAY)).toBe('2026-10')
    })

    it('当前月没记录 -> 跳到有记录的最新月份', () => {
        // 这是关键行为：放假回来的用户打开时，不该看到一片空白月历
        const list = [d('2025-11-11', 5), d('2025-09-08', 6), d('2025-10-01', 4)]
        expect(pickInitialMonth(list, TODAY)).toBe('2025-11')
    })

    it('跨年也能正确取到最新月份', () => {
        expect(pickInitialMonth([d('2025-12-31', 5)], TODAY)).toBe('2025-12')
    })

    it('完全不依赖入参顺序', () => {
        const asc = [d('2025-09-08', 6), d('2025-10-01', 4), d('2025-11-11', 5)]
        const desc = [...asc].reverse()
        expect(pickInitialMonth(asc, TODAY)).toBe('2025-11')
        expect(pickInitialMonth(desc, TODAY)).toBe('2025-11')
    })

    it('没有记录时返回当前月', () => {
        expect(pickInitialMonth([], TODAY)).toBe('2026-10')
        expect(pickInitialMonth(undefined, TODAY)).toBe('2026-10')
    })

    it('记录缺日期时返回当前月，不报错', () => {
        expect(pickInitialMonth([{ id: 1, moodScore: 5 }], TODAY)).toBe('2026-10')
    })
})
