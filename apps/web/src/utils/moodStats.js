/**
 * 情绪日记的派生数据计算。
 *
 * 为什么单独抽出来，而不是留在组件的 computed 里：
 *  1. 连续天数、月历首日偏移、按月分组这几处都有边界情况，值得单独测；
 *  2. 内联的话，测试必须挂载整个页面 —— 那要连带 mock element-plus 和 echarts，
 *     成本高且脆；
 *  3. 逻辑与视图分离，将来改 UI 不用把算法重推一遍。
 *
 * 本模块不依赖任何 UI 库行为，只依赖 dayjs 做日期运算。
 */
import { dayjs } from 'element-plus'

/** 有记录的最低分数，用于区分「没记录」和「记录了一个低分」 */
const NO_RECORD = 0

/**
 * 分数 -> 色阶档位（0-5）。
 * 0 表示无记录，1 最浅（情绪偏低）、5 最深（情绪较好）。
 * 刻意不用红色系：心理类产品不宜把「情绪差」渲染成警告色。
 */
export function moodLevel(score) {
    if (!score || score <= NO_RECORD) return 0
    if (score <= 2) return 1
    if (score <= 4) return 2
    if (score <= 6) return 3
    if (score <= 8) return 4
    return 5
}

/** 把日记数组转成「日期 -> 日记」的 Map，便于 O(1) 查某天 */
export function buildDiaryMap(diaries = []) {
    const m = new Map()
    diaries.forEach((d) => {
        if (d && d.diaryDate) m.set(d.diaryDate, d)
    })
    return m
}

/**
 * 连续记录天数。
 *
 * 规则：从今天往前数；**今天还没记录不算断**（否则用户一早打开就看到归零，
 * 会以为记录丢了），此时改从昨天起算。
 */
export function calcStreak(diaryMap, today = dayjs()) {
    let n = 0
    let cursor = dayjs(today).startOf('day')

    if (!diaryMap.has(cursor.format('YYYY-MM-DD'))) {
        cursor = cursor.subtract(1, 'day')
    }

    while (diaryMap.has(cursor.format('YYYY-MM-DD'))) {
        n += 1
        cursor = cursor.subtract(1, 'day')
    }
    return n
}

/**
 * 某个月的统计概览。
 * @param {string} month 'YYYY-MM'
 */
export function calcMonthStats(diaries = [], month = dayjs().format('YYYY-MM')) {
    const list = diaries.filter((d) => (d.diaryDate || '').startsWith(month))

    const scores = list.map((d) => d.moodScore).filter((s) => typeof s === 'number')
    const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0

    const freq = {}
    list.forEach((d) => {
        if (d.dominantEmotion) freq[d.dominantEmotion] = (freq[d.dominantEmotion] || 0) + 1
    })
    const top = Object.entries(freq).sort((a, b) => b[1] - a[1])[0]

    return {
        days: list.length,
        // 保留 1 位小数，避免出现 6.666666
        avg: Math.round(avg * 10) / 10,
        topEmotion: top ? top[0] : null
    }
}

/**
 * 生成月历格子。
 *
 * 前面用 null 补齐当月 1 号之前的空位（按周日为每周第一天），
 * 调用方据此渲染 7 列网格。
 *
 * @param {string} month 'YYYY-MM'
 * @returns {Array<{day:number,key:string,diary:object|null}|null>}
 */
export function buildCalendar(month, diaryMap = new Map()) {
    const start = dayjs(`${month}-01`).startOf('month')
    const cells = []

    for (let i = 0; i < start.day(); i += 1) cells.push(null)

    for (let d = 1; d <= start.daysInMonth(); d += 1) {
        const key = start.date(d).format('YYYY-MM-DD')
        cells.push({ day: d, key, diary: diaryMap.get(key) || null })
    }
    return cells
}

/**
 * 按月份分组，供历史列表展示。
 * @param {object} opts onlyLow 只看情绪偏低（<= lowThreshold）
 */
export function groupByMonth(diaries = [], { onlyLow = false, lowThreshold = 4 } = {}) {
    const list = onlyLow
        ? diaries.filter((d) => (d.moodScore ?? 10) <= lowThreshold)
        : diaries

    const map = new Map()
    list.forEach((d) => {
        const key = (d.diaryDate || '').slice(0, 7) || 'unknown'
        if (!map.has(key)) map.set(key, [])
        map.get(key).push(d)
    })

    return [...map.entries()].map(([month, items]) => ({
        month,
        label: month === 'unknown' ? '未标注日期' : dayjs(`${month}-01`).format('YYYY 年 M 月'),
        items
    }))
}

/**
 * 决定月历初始该显示哪个月（返回 'YYYY-MM'）。
 *
 * 规则：当前月有记录就显示当前月；否则显示**有记录的最新月份**。
 *
 * 为什么要有这条规则：历史记录都在几个月前的用户（很常见 —— 比如放完假回来），
 * 打开时如果停在当前月，看到的是一片空白月历，第一反应是「我的记录呢」。
 * 宁可把他送到有内容的地方，让他自己往前翻。
 *
 * 不依赖入参顺序（内部自行排序），避免调用方传未排序数组时取错。
 */
export function pickInitialMonth(diaries = [], today = dayjs()) {
    const cur = dayjs(today).format('YYYY-MM')
    if (!diaries.length) return cur

    const hasCurrent = diaries.some((d) => (d.diaryDate || '').startsWith(cur))
    if (hasCurrent) return cur

    const latest = diaries
        .map((d) => d.diaryDate)
        .filter(Boolean)
        .sort()
        .pop()

    return latest ? latest.slice(0, 7) : cur
}
