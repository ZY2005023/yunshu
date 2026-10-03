<template>
    <div class="emotionDiary-container">
        <div class="header-section">
            <div class="nd-container header-content">
                <el-image :src="iconUrl" class="header-icon"></el-image>
                <div class="header-text">
                    <h1>情绪日记</h1>
                    <p>每天一分钟，把今天的状态留下来</p>
                </div>
                <div class="header-streak">
                    <span class="streak-num">{{ streak }}</span>
                    <span class="streak-label">连续记录（天）</span>
                </div>
            </div>
        </div>

        <div class="content">
            <!-- ==================== 左栏：今日打卡 ==================== -->
            <div class="left-col">
                <!-- 危机求助卡：与对话的 crisis 事件、量表的自伤 alert 同一套资源。
                     修复前的缺口：用户在日记里写出高危内容，后端记了工单、
                     老师会收到通知，当事人自己却什么都看不到。 -->
                <el-alert
                    v-if="crisisCard"
                    type="error"
                    :closable="true"
                    class="crisis-alert"
                    @close="crisisCard = null"
                >
                    <template #title>
                        <strong>{{ crisisCard.title }}</strong>
                    </template>
                    <p class="crisis-subtitle">{{ crisisCard.subtitle }}</p>
                    <ul class="crisis-lines">
                        <li v-for="line in crisisCard.helplines" :key="line">{{ line }}</li>
                    </ul>
                    <p class="crisis-disclaimer">{{ crisisCard.disclaimer }}</p>
                </el-alert>

                <section class="diary-card checkin-card">
                    <div class="card-head">
                        <h2 class="title">今天感觉怎么样？</h2>
                        <span v-if="todayDiary" class="recorded-tip">
                            <el-icon><CircleCheck /></el-icon>
                            今天已记录，再次保存会更新
                        </span>
                    </div>

                    <!-- 情绪评分：滑块，拖动即选。保留 1-10 精度，但不需要点 10 次星星 -->
                    <div class="mood-picker">
                        <span class="mood-face">{{ currentFace }}</span>
                        <div class="mood-meta">
                            <p class="mood-score">
                                {{ diaryForm.moodScore ?? '—' }}<small>/10</small>
                            </p>
                            <p class="mood-text">
                                {{ diaryForm.moodScore ? emotionStatus[diaryForm.moodScore - 1] : '拖动滑块选择' }}
                            </p>
                        </div>
                    </div>
                    <el-slider
                        v-model="diaryForm.moodScore"
                        :min="1"
                        :max="10"
                        :show-tooltip="false"
                        class="mood-slider"
                    />

                    <!-- 主要情绪 -->
                    <p class="field-label">主要情绪</p>
                    <div class="emotion-grid">
                        <div
                            v-for="emotion in emotionOptions"
                            :key="emotion.name"
                            class="emotion-card"
                            :class="{ selected: emotion.name === diaryForm.dominantEmotion }"
                            @click="diaryForm.dominantEmotion = emotion.name"
                        >
                            <el-image :src="emotion.url" class="emotion-img"></el-image>
                            <div class="emotion-name">{{ emotion.name }}</div>
                        </div>
                    </div>

                    <!-- 睡眠 / 压力：分段按钮，比下拉快得多 -->
                    <div class="indicator-row">
                        <div class="indicator-group">
                            <p class="field-label">睡眠质量</p>
                            <div class="seg">
                                <button
                                    v-for="opt in SLEEP_OPTS"
                                    :key="opt.v"
                                    type="button"
                                    class="seg-item"
                                    :class="{ on: diaryForm.sleepQuality === opt.v }"
                                    @click="diaryForm.sleepQuality = opt.v"
                                >
                                    {{ opt.label }}
                                </button>
                            </div>
                        </div>
                        <div class="indicator-group">
                            <p class="field-label">压力水平</p>
                            <div class="seg">
                                <button
                                    v-for="opt in STRESS_OPTS"
                                    :key="opt.v"
                                    type="button"
                                    class="seg-item"
                                    :class="{ on: diaryForm.stressLevel === opt.v }"
                                    @click="diaryForm.stressLevel = opt.v"
                                >
                                    {{ opt.label }}
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- 详细记录折叠为选填：想写的人能写，不想写的人不被挡在门外 -->
                    <button type="button" class="more-toggle" @click="showMore = !showMore">
                        <el-icon><component :is="showMore ? 'ArrowDown' : 'ArrowRight'" /></el-icon>
                        {{ showMore ? '收起详细记录' : '想多说一点？（选填）' }}
                    </button>

                    <div v-show="showMore" class="more-fields">
                        <p class="field-label">情绪触发因素</p>
                        <el-input
                            v-model="diaryForm.emotionTriggers"
                            placeholder="今天什么事情影响了你的情绪？"
                            type="textarea"
                            :rows="2"
                            maxlength="1000"
                            show-word-limit
                        />
                        <p class="field-label">今日感想</p>
                        <el-input
                            v-model="diaryForm.diaryContent"
                            placeholder="写下今天的想法、感受，或发生的小事…"
                            type="textarea"
                            :rows="4"
                            maxlength="2000"
                            show-word-limit
                        />
                    </div>

                    <div class="actions">
                        <el-button @click="resetForm">清空</el-button>
                        <el-button type="primary" :loading="submitting" @click="submit">
                            {{ todayDiary ? '更新今天' : '保存记录' }}
                        </el-button>
                    </div>
                </section>
            </div>

            <!-- ==================== 右栏：回看与洞察 ==================== -->
            <div class="right-col">
                <!-- 本月概览 -->
                <section class="overview">
                    <div class="ov-item">
                        <b>{{ monthStats.days }}</b>
                        <span>本月记录</span>
                    </div>
                    <div class="ov-item">
                        <b>{{ monthStats.avg || '—' }}</b>
                        <span>平均分</span>
                    </div>
                    <div class="ov-item">
                        <b class="ov-text">{{ monthStats.topEmotion || '—' }}</b>
                        <span>最常见情绪</span>
                    </div>
                </section>

                <!-- AI 情绪分析（提交后即时展示） -->
                <section v-if="aiFeedback" class="diary-card ai-feedback">
                    <h2 class="title">
                        <el-icon><MagicStick /></el-icon>
                        AI 情绪分析
                    </h2>
                    <div class="feedback-body">
                        <div class="feedback-row">
                            <span class="label">主要情绪</span>
                            <el-tag>{{ aiFeedback.primaryEmotion || '—' }}</el-tag>
                            <span class="label label--gap">风险等级</span>
                            <el-tag :type="riskTagType(aiFeedback.riskLevel)">
                                {{ riskText(aiFeedback.riskLevel) }}
                            </el-tag>
                        </div>
                        <p v-if="aiFeedback.summary" class="feedback-summary">{{ aiFeedback.summary }}</p>
                        <div v-if="aiFeedback.suggestion" class="feedback-suggestion">
                            {{ aiFeedback.suggestion }}
                        </div>
                        <ul
                            v-if="aiFeedback.improvementSuggestions && aiFeedback.improvementSuggestions.length"
                            class="feedback-list"
                        >
                            <li v-for="(tip, i) in aiFeedback.improvementSuggestions" :key="i">{{ tip }}</li>
                        </ul>
                    </div>
                </section>

                <!-- 情绪月历：一眼看到整月哪天状态差 -->
                <section class="diary-card">
                    <div class="card-head">
                        <h2 class="title">情绪月历</h2>
                        <div class="cal-nav">
                            <!-- 翻到别的月份时给一个回最新记录的快捷入口 -->
                            <button
                                v-if="latestDiaryMonth && !isOnLatestMonth"
                                type="button"
                                class="cal-latest"
                                @click="jumpToLatest"
                            >
                                最新记录
                            </button>
                            <button type="button" class="cal-btn" @click="shiftMonth(-1)">
                                <el-icon><ArrowLeft /></el-icon>
                            </button>
                            <span class="cal-label">{{ calMonth.format('YYYY 年 M 月') }}</span>
                            <button
                                type="button"
                                class="cal-btn"
                                :disabled="isCurrentMonth"
                                @click="shiftMonth(1)"
                            >
                                <el-icon><ArrowRight /></el-icon>
                            </button>
                        </div>
                    </div>

                    <p class="cal-summary">
                        <template v-if="myDiaries.length">
                            共 <b>{{ myDiaries.length }}</b> 条记录
                            <span v-if="rangeText"> · {{ rangeText }}</span>
                        </template>
                        <template v-else>还没有记录，从今天开始写第一篇吧</template>
                    </p>

                    <div class="cal-weekdays">
                        <span v-for="w in ['日', '一', '二', '三', '四', '五', '六']" :key="w">{{ w }}</span>
                    </div>
                    <div class="cal-grid">
                        <template v-for="(cell, i) in calendarCells" :key="i">
                            <span v-if="!cell" class="cal-cell cal-cell--empty"></span>
                            <button
                                v-else
                                type="button"
                                class="cal-cell"
                                :class="[cellClass(cell.diary), { today: cell.key === todayKey }]"
                                :title="cellTitle(cell)"
                                @click="openDetail(cell)"
                            >
                                {{ cell.day }}
                            </button>
                        </template>
                    </div>

                    <div class="cal-legend">
                        <span class="legend-text">情绪偏低</span>
                        <span v-for="n in 5" :key="n" class="legend-dot" :class="`lv-${n}`"></span>
                        <span class="legend-text">情绪较好</span>
                    </div>
                </section>

                <!-- 情绪趋势 -->
                <section class="diary-card">
                    <div class="card-head">
                        <h2 class="title">情绪趋势</h2>
                        <span class="sub-hint">虚线为这段时间的平均分</span>
                    </div>
                    <div v-show="myDiaries.length > 1" ref="trendChartRef" class="trend-chart"></div>
                    <div v-if="myDiaries.length <= 1" class="nd-empty">
                        <span class="nd-empty-icon"><el-icon><TrendCharts /></el-icon></span>
                        <p>记录满 2 天后，这里会出现你的情绪曲线</p>
                    </div>
                </section>

                <!-- 历史记录 -->
                <section class="diary-card">
                    <div class="card-head">
                        <h2 class="title">历史记录</h2>
                        <el-checkbox v-model="onlyLow" size="small">只看情绪偏低（≤4 分）</el-checkbox>
                    </div>

                    <template v-if="groupedHistory.length">
                        <div v-for="g in groupedHistory" :key="g.month" class="history-group">
                            <p class="group-label">
                                {{ g.label }}
                                <span class="group-count">{{ g.items.length }} 条</span>
                            </p>
                            <div
                                v-for="d in g.items"
                                :key="d.id"
                                class="history-item"
                                @click="openDiary(d)"
                            >
                                <div class="history-head">
                                    <span class="history-date">{{ d.diaryDate }}</span>
                                    <el-rate v-model="d.moodScore" disabled :max="10" size="small" />
                                    <el-tag v-if="d.dominantEmotion" size="small">{{ d.dominantEmotion }}</el-tag>
                                    <el-tag
                                        v-if="d.aiEmotionAnalysis"
                                        size="small"
                                        :type="riskTagType(d.aiEmotionAnalysis.riskLevel)"
                                    >
                                        {{ riskText(d.aiEmotionAnalysis.riskLevel) }}
                                    </el-tag>
                                </div>
                                <div v-if="d.diaryContent" class="history-content">{{ d.diaryContent }}</div>
                            </div>
                        </div>
                    </template>

                    <div v-else class="nd-empty">
                        <span class="nd-empty-icon"><el-icon><Notebook /></el-icon></span>
                        <p>{{ onlyLow ? '没有情绪偏低的记录，这挺好的' : '还没有记录，写下第一篇日记吧' }}</p>
                    </div>
                </section>
            </div>
        </div>

        <!-- 某一天的完整记录 -->
        <el-dialog v-model="detailVisible" :title="detailTitle" width="520px">
            <div v-if="detailDiary" class="detail-body">
                <div class="detail-row">
                    <span class="detail-label">情绪评分</span>
                    <el-rate v-model="detailDiary.moodScore" disabled :max="10" />
                </div>
                <div class="detail-row">
                    <span class="detail-label">主要情绪</span>
                    <el-tag v-if="detailDiary.dominantEmotion">{{ detailDiary.dominantEmotion }}</el-tag>
                    <span v-else class="nd-muted">未填写</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">睡眠 / 压力</span>
                    <span>
                        {{ labelOf(SLEEP_OPTS, detailDiary.sleepQuality) }} /
                        {{ labelOf(STRESS_OPTS, detailDiary.stressLevel) }}
                    </span>
                </div>
                <template v-if="detailDiary.emotionTriggers">
                    <p class="detail-label">触发因素</p>
                    <p class="detail-text">{{ detailDiary.emotionTriggers }}</p>
                </template>
                <template v-if="detailDiary.diaryContent">
                    <p class="detail-label">今日感想</p>
                    <p class="detail-text">{{ detailDiary.diaryContent }}</p>
                </template>
                <template v-if="detailDiary.aiEmotionAnalysis && detailDiary.aiEmotionAnalysis.suggestion">
                    <p class="detail-label">AI 建议</p>
                    <p class="detail-text detail-text--ai">{{ detailDiary.aiEmotionAnalysis.suggestion }}</p>
                </template>
            </div>
            <div v-else class="nd-empty">
                <p>这一天没有记录</p>
            </div>
        </el-dialog>
    </div>
</template>

<script setup>
/**
 * 情绪日记。
 *
 * 改版依据（调研同类产品后确定）：
 *  1. 情绪类产品留存的第一杀手是**录入摩擦力** —— Daylio 的核心竞争力就是「两次点击完成」。
 *     原来是 6 个字段平铺 + 2 个下拉 + 10 颗星，像写作业。现在改为
 *     滑块选分（保留 1-10 精度）、分段按钮选睡眠/压力、详细记录折叠成选填。
 *  2. 第二是**缺少一眼看全貌的视图** —— 「Year in Pixels」/ 情绪日历是这类产品的标配。
 *     新增月历热力图，一眼看出本月哪天状态差。
 *  3. 新增连续记录天数与本月统计，给习惯一个正反馈。
 *  4. 历史从无限长列表改为按月分组 + 只看低分筛选，让旧记录可回看。
 *
 * 全部基于现有 `/emotion-diary/my` 返回的数据计算，**未改动任何后端接口**。
 */
import { dayjs, ElMessage } from 'element-plus'
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { addEmotionDiary, getMyDiaries } from '@/api/frontend'
import {
    buildCalendar,
    buildDiaryMap,
    calcMonthStats,
    calcStreak,
    groupByMonth,
    moodLevel,
    pickInitialMonth
} from '@/utils/moodStats'
import {
    CRISIS_CARD_SUBTITLE,
    CRISIS_CARD_TITLE,
    CRISIS_DISCLAIMER,
    CRISIS_HELPLINES
} from '@/utils/crisisResources'
import * as echarts from 'echarts'

// 提交状态 / AI反馈 / 我的日记
const submitting = ref(false)
// 危机求助卡（保存后按规则层命中等级 / 模型风险等级展示，见 updateCrisisCard）
const crisisCard = ref(null)
const aiFeedback = ref(null)
const myDiaries = ref([])
const trendChartRef = ref(null)
let trendChart = null

// 详细记录默认收起
const showMore = ref(false)
// 只看低分
const onlyLow = ref(false)

const todayKey = dayjs().format('YYYY-MM-DD')

/** 原版的 10 档情绪文案，保持不动 */
const emotionStatus = [
    '绝望崩溃',
    '消沉抑郁',
    '焦虑烦躁',
    '低落不悦',
    '平静淡然',
    '轻松惬意',
    '愉悦舒心',
    '欢欣满足',
    '兴奋欣喜',
    '极致幸福'
]

/** 滑块旁的表情：每 2 分一档 */
const MOOD_FACES = ['😣', '😣', '😔', '😔', '😌', '😌', '🙂', '🙂', '😄', '😄']

const SLEEP_OPTS = [
    { v: 1, label: '很差' },
    { v: 2, label: '较差' },
    { v: 3, label: '一般' },
    { v: 4, label: '良好' },
    { v: 5, label: '很好' }
]
const STRESS_OPTS = [
    { v: 1, label: '很低' },
    { v: 2, label: '较低' },
    { v: 3, label: '中等' },
    { v: 4, label: '较高' },
    { v: 5, label: '很高' }
]

const emotionOptions = [
    { name: '开心', url: new URL('@/assets/images/开心.png', import.meta.url).href },
    { name: '平静', url: new URL('@/assets/images/平静.png', import.meta.url).href },
    { name: '焦虑', url: new URL('@/assets/images/焦虑.png', import.meta.url).href },
    { name: '悲伤', url: new URL('@/assets/images/悲伤.png', import.meta.url).href },
    { name: '兴奋', url: new URL('@/assets/images/兴奋.png', import.meta.url).href },
    { name: '疲惫', url: new URL('@/assets/images/疲惫.png', import.meta.url).href },
    { name: '惊讶', url: new URL('@/assets/images/惊讶.png', import.meta.url).href },
    { name: '困惑', url: new URL('@/assets/images/困惑.png', import.meta.url).href }
]

const diaryForm = reactive({
    diaryDate: todayKey,
    moodScore: null,
    dominantEmotion: '',
    emotionTriggers: '',
    diaryContent: '',
    sleepQuality: null,
    stressLevel: null
})

/** 滑块旁的表情与文案随分数实时变化（放在 diaryForm 之后，避免依赖声明顺序） */
const currentFace = computed(() =>
    diaryForm.moodScore ? MOOD_FACES[diaryForm.moodScore - 1] : '🫥'
)

const riskText = (level) => {
    const map = { 0: '正常', 1: '关注', 2: '预警', 3: '危机' }
    return map[level] ?? '正常'
}
const riskTagType = (level) => {
    const map = { 0: 'success', 1: 'info', 2: 'warning', 3: 'danger' }
    return map[level] ?? 'info'
}

const labelOf = (opts, v) => opts.find((o) => o.v === v)?.label || '—'

// ==================== 派生数据（全部前端计算，不新增接口） ====================

/** 日期 -> 日记，便于 O(1) 取值 */
const diaryByDate = computed(() => buildDiaryMap(myDiaries.value))

const todayDiary = computed(() => diaryByDate.value.get(todayKey) || null)

/** 连续记录：今天还没记录不算断（规则与边界见 utils/moodStats） */
const streak = computed(() => calcStreak(diaryByDate.value))

/** 本月概览 */
const monthStats = computed(() => calcMonthStats(myDiaries.value))

/** 月历 */
const calMonth = ref(dayjs().startOf('month'))
const isCurrentMonth = computed(() => calMonth.value.isSame(dayjs(), 'month'))

/** 最新一条记录所在的月份（'YYYY-MM'）。myDiaries 由后端按日期倒序返回 */
const latestDiaryMonth = computed(() => {
    const latest = myDiaries.value.find((d) => d.diaryDate)
    return latest ? latest.diaryDate.slice(0, 7) : null
})

const isOnLatestMonth = computed(
    () =>
        !latestDiaryMonth.value ||
        calMonth.value.format('YYYY-MM') === latestDiaryMonth.value
)

/** 记录总数与日期范围 —— 让用户一眼知道「到底有没有以往记录」 */
const rangeText = computed(() => {
    const dates = myDiaries.value.map((d) => d.diaryDate).filter(Boolean).sort()
    if (dates.length < 2) return ''
    return `${dates[0]} 至 ${dates[dates.length - 1]}`
})

/**
 * 首次加载时定位月份。
 *
 * 当前月有记录才停在当前月；否则直接跳到「有记录的最新月份」——
 * 否则历史记录都在几个月前的用户，打开看到的是一片空白月历，
 * 会以为记录丢了。（老数据跨月时这个问题特别明显。）
 */
let calInitialized = false
const locateInitialMonth = () => {
    if (calInitialized || !myDiaries.value.length) return
    calInitialized = true
    calMonth.value = dayjs(`${pickInitialMonth(myDiaries.value)}-01`).startOf('month')
}

const jumpToLatest = () => {
    if (latestDiaryMonth.value) {
        calMonth.value = dayjs(`${latestDiaryMonth.value}-01`).startOf('month')
    }
}

const calendarCells = computed(() =>
    buildCalendar(calMonth.value.format('YYYY-MM'), diaryByDate.value)
)

const shiftMonth = (delta) => {
    calMonth.value = calMonth.value.add(delta, 'month')
}

/** 分数 -> 色阶类名（低分浅、高分深，全用品牌青绿，不引入刺眼的红） */
const cellClass = (diary) => `lv-${moodLevel(diary && diary.moodScore)}`

const cellTitle = (cell) => {
    if (!cell.diary?.moodScore) return `${cell.key}（无记录）`
    return `${cell.key} ${cell.diary.moodScore} 分 ${cell.diary.dominantEmotion || ''}`
}

/** 历史按月分组（可选只看低分） */
const groupedHistory = computed(() => groupByMonth(myDiaries.value, { onlyLow: onlyLow.value }))

// ==================== 详情弹窗 ====================
const detailVisible = ref(false)
const detailDiary = ref(null)
const detailDate = ref('')
const detailTitle = computed(() => detailDate.value || '记录详情')

const openDetail = (cell) => {
    detailDiary.value = cell.diary
    detailDate.value = dayjs(cell.key).format('YYYY 年 M 月 D 日')
    detailVisible.value = true
}

const openDiary = (d) => {
    detailDiary.value = d
    detailDate.value = d.diaryDate ? dayjs(d.diaryDate).format('YYYY 年 M 月 D 日') : '记录详情'
    detailVisible.value = true
}

// ==================== 数据加载 ====================
const parseAnalysis = (raw) => {
    if (!raw) return null
    try {
        return typeof raw === 'string' ? JSON.parse(raw) : raw
    } catch (e) {
        return null
    }
}

/** 今天若已有记录则回填，让用户能直接看到/修改，而不是重新填一遍 */
const fillToday = () => {
    const t = todayDiary.value
    if (!t) return
    Object.assign(diaryForm, {
        diaryDate: t.diaryDate,
        moodScore: t.moodScore,
        dominantEmotion: t.dominantEmotion || '',
        emotionTriggers: t.emotionTriggers || '',
        diaryContent: t.diaryContent || '',
        sleepQuality: t.sleepQuality ?? null,
        stressLevel: t.stressLevel ?? null
    })
    // 有内容就展开，否则用户会以为记录丢了
    if (t.emotionTriggers || t.diaryContent) showMore.value = true
    aiFeedback.value = parseAnalysis(t.aiEmotionAnalysis)
}

const loadMyDiaries = () => {
    getMyDiaries().then((res) => {
        myDiaries.value = res || []
        locateInitialMonth()
        fillToday()
        nextTick(() => renderTrend())
    })
}

const renderTrend = () => {
    if (!trendChartRef.value || myDiaries.value.length < 2) return
    if (!trendChart) trendChart = echarts.init(trendChartRef.value)

    const sorted = [...myDiaries.value].sort((a, b) => (a.diaryDate > b.diaryDate ? 1 : -1))
    const scores = sorted.map((d) => d.moodScore).filter((s) => typeof s === 'number')
    const avg = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0

    trendChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 42, right: 22, top: 26, bottom: 32 },
        xAxis: {
            type: 'category',
            data: sorted.map((d) => d.diaryDate),
            axisLabel: { color: '#6d837c', fontSize: 11 },
            axisLine: { lineStyle: { color: '#e2ece9' } }
        },
        yAxis: {
            type: 'value',
            min: 0,
            max: 10,
            axisLabel: { color: '#6d837c', fontSize: 11 },
            splitLine: { lineStyle: { color: '#f0f5f4' } }
        },
        series: [
            {
                name: '情绪评分',
                type: 'line',
                smooth: true,
                symbolSize: 7,
                data: sorted.map((d) => d.moodScore),
                lineStyle: { width: 3, color: '#52b2a4' },
                itemStyle: { color: '#52b2a4' },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(82,178,164,0.28)' },
                            { offset: 1, color: 'rgba(82,178,164,0.02)' }
                        ]
                    }
                },
                // 平均线：让「最近比平时低还是高」一眼可见
                markLine: {
                    silent: true,
                    symbol: 'none',
                    label: {
                        formatter: `平均 ${Math.round(avg * 10) / 10}`,
                        color: '#6d837c',
                        fontSize: 11,
                        position: 'insideEndTop'
                    },
                    lineStyle: { type: 'dashed', color: '#7cc9bf', width: 1 },
                    data: [{ yAxis: Math.round(avg * 10) / 10 }]
                }
            }
        ]
    })
}

// ==================== 提交 ====================
const resetForm = () => {
    Object.assign(diaryForm, {
        diaryDate: todayKey,
        moodScore: null,
        dominantEmotion: '',
        emotionTriggers: '',
        diaryContent: '',
        sleepQuality: null,
        stressLevel: null
    })
    aiFeedback.value = null
    crisisCard.value = null
}

const submit = () => {
    if (!diaryForm.moodScore) {
        ElMessage.error('请先选择情绪评分')
        return
    }
    submitting.value = true
    addEmotionDiary(diaryForm)
        .then((res) => {
            ElMessage.success(todayDiary.value ? '已更新今天的记录' : '记录成功')
            // 后端保存后会自动做 AI 分析
            aiFeedback.value = parseAnalysis(res && res.aiEmotionAnalysis)
            updateCrisisCard(res, aiFeedback.value)
            loadMyDiaries()
        })
        .catch(() => {
            ElMessage.error('提交失败，请稍后重试')
        })
        .finally(() => {
            submitting.value = false
        })
}

/**
 * 危机求助卡的触发条件，与后端两条升级路径对齐：
 *  · 规则层命中（响应的 crisisLevel > 0）—— 与对话的 crisis 事件同一阈值
 *    （level 1「难过/失眠」也弹，宁可不报不漏报）；
 *  · 模型层 riskLevel >= 2 —— 与后端 LLM_RISK_THRESHOLD 一致。
 * 资源是固定常量（utils/crisisResources.js），不依赖 AI 是否配置。
 */
const updateCrisisCard = (res, analysis) => {
    const ruleLevel = Number((res && res.crisisLevel) || 0)
    const llmLevel = Number((analysis && analysis.riskLevel) || 0)
    if (ruleLevel > 0 || llmLevel >= 2) {
        crisisCard.value = {
            title: CRISIS_CARD_TITLE,
            subtitle: CRISIS_CARD_SUBTITLE,
            helplines: CRISIS_HELPLINES,
            disclaimer: CRISIS_DISCLAIMER
        }
    } else {
        crisisCard.value = null
    }
}

const iconUrl = new URL('@/assets/images/like.png', import.meta.url).href

const onResize = () => trendChart?.resize()

onMounted(() => {
    loadMyDiaries()
    window.addEventListener('resize', onResize)
})

// 卸载时释放 ECharts 实例（P0-7 / F9）
onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    trendChart?.dispose()
    trendChart = null
})
</script>

<style lang="scss" scoped>
.emotionDiary-container {
    min-height: calc(100vh - var(--nd-navbar-h));
    background: var(--nd-bg);

    /* ---------- 顶部 ---------- */
    .header-section {
        padding: 32px 0;
        color: #fff;
        background: linear-gradient(120deg, #23857a 0%, #1c6b63 60%, #175450 100%);

        .header-content {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .header-icon {
            flex: none;
            width: 52px;
            height: 52px;
        }
        .header-text {
            flex: 1;
            min-width: 0;

            h1 {
                font-size: 24px;
                color: #fff;
            }
            p {
                margin-top: 4px;
                font-size: 13.5px;
                color: rgba(255, 255, 255, 0.72);
            }
        }
        .header-streak {
            flex: none;
            text-align: center;
            padding: 6px 18px;
            border-radius: var(--nd-radius);
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.18);

            .streak-num {
                display: block;
                font-size: 26px;
                font-weight: 700;
                line-height: 1.1;
                color: #fff;
            }
            .streak-label {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.7);
            }
        }
    }

    /* ---------- 双栏 ---------- */
    .content {
        display: flex;
        align-items: flex-start;
        gap: var(--nd-gap-lg);
        max-width: 1200px;
        width: 100%;
        margin: 0 auto;
        padding: var(--nd-gap-lg);

        .left-col {
            flex: 0 0 500px;

            /* 危机求助卡 —— 与对话页 crisis 卡片、量表页自伤 alert 同一口径 */
            .crisis-alert {
                margin-bottom: var(--nd-gap);
                padding: 14px 16px;

                .crisis-subtitle {
                    margin: 6px 0 10px;
                    font-size: 13px;
                    color: var(--nd-text-2);
                }
                .crisis-lines {
                    margin: 0 0 10px;
                    padding-left: 18px;
                    font-size: 13.5px;
                    line-height: 1.9;

                    li strong {
                        font-weight: 700;
                    }
                }
                .crisis-disclaimer {
                    margin: 0;
                    font-size: 12px;
                    color: var(--nd-text-3);
                }
            }
        }
        .right-col {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: var(--nd-gap);
        }
    }

    /* ---------- 卡片 ---------- */
    .diary-card {
        padding: 22px;
        margin-bottom: var(--nd-gap);
        background: var(--nd-surface);
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius);
        box-shadow: var(--nd-shadow-xs);

        &:last-child {
            margin-bottom: 0;
        }
    }

    .card-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 18px;
    }

    .title {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 17px;
        font-weight: 600;
        color: var(--nd-text-1);
    }

    .sub-hint {
        font-size: 12px;
        color: var(--nd-text-4);
    }

    .recorded-tip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        font-size: 12.5px;
        color: var(--nd-success);
    }

    .field-label {
        margin: 20px 0 10px;
        font-size: 13px;
        font-weight: 500;
        color: var(--nd-text-3);
    }

    /* ---------- 情绪评分 ---------- */
    .mood-picker {
        display: flex;
        align-items: center;
        gap: 16px;

        .mood-face {
            font-size: 44px;
            line-height: 1;
        }
        .mood-meta {
            .mood-score {
                font-size: 26px;
                font-weight: 700;
                line-height: 1.1;
                color: var(--nd-text-1);

                small {
                    font-size: 13px;
                    font-weight: 400;
                    color: var(--nd-text-4);
                    margin-left: 2px;
                }
            }
            .mood-text {
                margin-top: 2px;
                font-size: 13.5px;
                color: var(--nd-primary-600);
            }
        }
    }

    .mood-slider {
        margin: 6px 6px 0;
        --el-slider-main-bg-color: var(--nd-primary-500);
        --el-slider-runway-bg-color: var(--nd-primary-100);
    }

    /* ---------- 情绪选择 ---------- */
    .emotion-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;

        .emotion-card {
            padding: 10px 4px;
            border: 1.5px solid var(--nd-border);
            border-radius: var(--nd-radius-sm);
            background: var(--nd-surface-soft);
            text-align: center;
            cursor: pointer;
            transition: all var(--nd-duration) var(--nd-ease);

            &:hover {
                border-color: var(--nd-primary-200);
            }

            &.selected {
                border-color: var(--nd-primary-500);
                background: var(--nd-primary-50);
                transform: translateY(-2px);
                box-shadow: var(--nd-shadow-sm);
            }

            .emotion-img {
                width: 32px;
                height: 32px;
                margin: 0 auto;
            }
            .emotion-name {
                margin-top: 4px;
                font-size: 12.5px;
                color: var(--nd-text-2);
            }
        }
    }

    /* ---------- 睡眠 / 压力分段按钮 ---------- */
    .indicator-row {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
    }

    .seg {
        display: flex;
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius-sm);
        overflow: hidden;

        .seg-item {
            flex: 1;
            padding: 8px 0;
            border: 0;
            border-right: 1px solid var(--nd-border);
            background: var(--nd-surface);
            font-size: 12.5px;
            color: var(--nd-text-3);
            cursor: pointer;
            transition: all var(--nd-duration) var(--nd-ease);

            &:last-child {
                border-right: 0;
            }
            &:hover {
                background: var(--nd-primary-50);
                color: var(--nd-primary-600);
            }
            &.on {
                background: var(--nd-primary-500);
                color: #fff;
                font-weight: 500;
            }
        }
    }

    /* ---------- 折叠的详细记录 ---------- */
    .more-toggle {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-top: 22px;
        padding: 0;
        border: 0;
        background: none;
        font-size: 13.5px;
        color: var(--nd-primary-600);
        cursor: pointer;

        &:hover {
            text-decoration: underline;
        }
    }

    .more-fields {
        margin-top: 4px;
    }

    .actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 24px;
    }

    /* ---------- 本月概览 ---------- */
    .overview {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: var(--nd-gap);
        padding: 18px;
        background: var(--nd-surface);
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius);
        box-shadow: var(--nd-shadow-xs);
        text-align: center;

        .ov-item {
            b {
                display: block;
                font-size: 24px;
                font-weight: 700;
                line-height: 1.2;
                color: var(--nd-primary-600);
            }
            .ov-text {
                font-size: 17px;
                padding: 4px 0;
            }
            span {
                font-size: 12.5px;
                color: var(--nd-text-3);
            }
        }
    }

    /* ---------- AI 反馈 ---------- */
    .ai-feedback {
        background: linear-gradient(135deg, var(--nd-primary-50), #f4fbf9);
        border-color: var(--nd-primary-200);

        .feedback-body {
            .feedback-row {
                display: flex;
                align-items: center;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 12px;

                .label {
                    font-size: 13px;
                    color: var(--nd-text-3);
                }
                .label--gap {
                    margin-left: 12px;
                }
            }
            .feedback-summary {
                margin-bottom: 10px;
                font-size: 14.5px;
                line-height: 1.75;
                color: var(--nd-text-2);
            }
            .feedback-suggestion {
                margin-bottom: 10px;
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.72);
                border-left: 3px solid var(--nd-primary-400);
                border-radius: 0 var(--nd-radius-sm) var(--nd-radius-sm) 0;
                font-size: 13.5px;
                line-height: 1.75;
                color: var(--nd-text-2);
            }
            .feedback-list {
                padding-left: 18px;

                li {
                    margin-bottom: 6px;
                    font-size: 13.5px;
                    line-height: 1.7;
                    color: var(--nd-text-3);
                    list-style: disc;
                }
            }
        }
    }

    /* ---------- 月历 ---------- */
    .cal-nav {
        display: flex;
        align-items: center;
        gap: 6px;

        .cal-latest {
            margin-right: 4px;
            padding: 4px 10px;
            border: 1px solid var(--nd-primary-200);
            border-radius: var(--nd-radius-full);
            background: var(--nd-primary-50);
            font-size: 12px;
            color: var(--nd-primary-700);
            cursor: pointer;
            transition: background var(--nd-duration) var(--nd-ease);

            &:hover {
                background: var(--nd-primary-100);
            }
        }

        .cal-label {
            min-width: 92px;
            font-size: 13px;
            text-align: center;
            color: var(--nd-text-2);
        }
        .cal-btn {
            width: 26px;
            height: 26px;
            display: grid;
            place-items: center;
            border: 1px solid var(--nd-border);
            border-radius: var(--nd-radius-xs);
            background: var(--nd-surface);
            color: var(--nd-text-3);
            cursor: pointer;

            &:hover:not(:disabled) {
                color: var(--nd-primary-600);
                border-color: var(--nd-primary-200);
            }
            &:disabled {
                opacity: 0.4;
                cursor: not-allowed;
            }
        }
    }

    .cal-summary {
        margin-bottom: 12px;
        font-size: 12.5px;
        color: var(--nd-text-4);

        b {
            color: var(--nd-primary-600);
        }
    }

    .cal-weekdays,
    .cal-grid {
        display: grid;
        grid-template-columns: repeat(7, 1fr);
        gap: 5px;
    }

    .cal-weekdays {
        margin-bottom: 6px;

        span {
            font-size: 11.5px;
            text-align: center;
            color: var(--nd-text-4);
        }
    }

    .cal-cell {
        aspect-ratio: 1;
        display: grid;
        place-items: center;
        border: 1px solid transparent;
        border-radius: var(--nd-radius-xs);
        font-size: 12.5px;
        color: var(--nd-text-2);
        background: var(--nd-surface-soft);
        cursor: pointer;
        transition: transform var(--nd-duration) var(--nd-ease);

        &:hover {
            transform: scale(1.08);
        }

        &--empty {
            background: transparent;
            cursor: default;
            &:hover {
                transform: none;
            }
        }

        /* 色阶：统一青绿深浅，低分不用红色（心理产品不宜强化负面） */
        &.lv-0 {
            background: var(--nd-surface-soft);
            color: var(--nd-text-4);
        }
        &.lv-1 {
            background: #e4f2ef;
            color: var(--nd-text-2);
        }
        &.lv-2 {
            background: #cbe7e1;
            color: var(--nd-text-1);
        }
        &.lv-3 {
            background: #a8d8d0;
            color: var(--nd-text-1);
        }
        &.lv-4 {
            background: #7cc9bf;
            color: #0f3733;
        }
        &.lv-5 {
            background: #52b2a4;
            color: #fff;
            font-weight: 600;
        }

        &.today {
            border-color: var(--nd-primary-600);
            box-shadow: 0 0 0 2px rgba(47, 156, 139, 0.16);
        }
    }

    .cal-legend {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        margin-top: 14px;

        .legend-text {
            font-size: 11.5px;
            color: var(--nd-text-4);
        }
        .legend-dot {
            width: 12px;
            height: 12px;
            border-radius: 3px;

            &.lv-1 {
                background: #e4f2ef;
            }
            &.lv-2 {
                background: #cbe7e1;
            }
            &.lv-3 {
                background: #a8d8d0;
            }
            &.lv-4 {
                background: #7cc9bf;
            }
            &.lv-5 {
                background: #52b2a4;
            }
        }
    }

    /* ---------- 趋势 ---------- */
    .trend-chart {
        width: 100%;
        height: 220px;
    }

    /* ---------- 历史 ---------- */
    .history-group {
        & + .history-group {
            margin-top: 18px;
        }

        .group-label {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 600;
            color: var(--nd-text-2);

            .group-count {
                font-size: 11.5px;
                font-weight: 400;
                color: var(--nd-text-4);
            }
        }
    }

    .history-item {
        padding: 12px 14px;
        margin-bottom: 8px;
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius-sm);
        cursor: pointer;
        transition: all var(--nd-duration) var(--nd-ease);

        &:hover {
            border-color: var(--nd-primary-200);
            background: var(--nd-primary-50);
        }

        .history-head {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;

            .history-date {
                font-size: 13.5px;
                font-weight: 600;
                color: var(--nd-text-1);
            }
        }

        .history-content {
            margin-top: 8px;
            font-size: 13.5px;
            line-height: 1.7;
            color: var(--nd-text-3);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
    }

    /* ---------- 详情弹窗 ---------- */
    .detail-body {
        .detail-row {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 0;
            border-bottom: 1px dashed var(--nd-border);
        }
        .detail-label {
            margin: 14px 0 6px;
            font-size: 13px;
            font-weight: 600;
            color: var(--nd-text-3);

            &:first-child {
                margin-top: 0;
            }
        }
        .detail-text {
            font-size: 14px;
            line-height: 1.8;
            color: var(--nd-text-2);
            white-space: pre-wrap;

            &--ai {
                padding: 12px 14px;
                background: var(--nd-primary-50);
                border-left: 3px solid var(--nd-primary-400);
                border-radius: 0 var(--nd-radius-sm) var(--nd-radius-sm) 0;
            }
        }
    }

    /* ---------- 响应式 ---------- */
    @media (max-width: 1024px) {
        .content {
            flex-direction: column;

            .left-col,
            .right-col {
                flex: 1 1 auto;
                width: 100%;
            }
        }
    }

    @media (max-width: 640px) {
        .header-section {
            padding: 24px 0;

            .header-streak {
                display: none;
            }
        }
        .content {
            padding: var(--nd-gap);
        }
        .diary-card {
            padding: 16px;
        }
        .indicator-row {
            grid-template-columns: 1fr;
        }
        .overview {
            gap: 8px;
            padding: 14px;
        }
        .emotion-grid {
            gap: 6px;
        }
    }
}
</style>
