/**
 * 看板图表的数据整形 —— 纯函数，可与 echarts 解耦单独测。
 *
 * 为什么要有这一层：原来 `data: TrendData.map(item => item.avgMoodScore)` 直接内联在
 * `dashboard.vue` 里，导致一个**会误导人的显示问题**藏了很久 ——
 *
 * 后端对「当天没有日记」返回 `avgMoodScore = 0`（Java 版遗留口径），
 * 但 `mood_score` 的合法范围是 **1~10，0 根本不是有效评分**。
 * 直接画 0 会在图上呈现成一条趴在底部的线，看起来像「全体用户情绪跌到谷底」，
 * 实际只是「那天没人记录」。心理健康看板上这种误读代价很高。
 */

/**
 * 情绪评分序列。**无记录的天返回 null**，让 echarts 断开折线而不是画到 0。
 *
 * @param {Array<{date: string, avgMoodScore: number, recordCount: number}>} trendData
 * @returns {Array<number|null>}
 */
export function toMoodSeries(trendData = []) {
    return trendData.map((d) => {
        const count = Number(d?.recordCount ?? 0)
        if (!Number.isFinite(count) || count <= 0) return null
        const score = Number(d?.avgMoodScore)
        return Number.isFinite(score) ? score : null
    })
}

/**
 * 记录数量序列。**无记录的天就是 0**（那天确实记录了 0 条），不需要置 null。
 */
export function toCountSeries(trendData = []) {
    return trendData.map((d) => {
        const count = Number(d?.recordCount ?? 0)
        return Number.isFinite(count) ? count : 0
    })
}

/**
 * 有记录的天数 —— 用来说明「这条线覆盖了几天」。
 * 数据稀疏时（例如 7 天里只有 2 天有人记录），看板应当能提示，
 * 否则单看一条折线会以为数据很完整。
 */
export function countDaysWithData(trendData = []) {
    return trendData.filter((d) => Number(d?.recordCount ?? 0) > 0).length
}
