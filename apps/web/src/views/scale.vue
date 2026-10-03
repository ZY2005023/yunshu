<template>
    <div class="scale-page">
        <!-- ============ 选量表 ============ -->
        <div class="intro">
            <h2>心理自评量表</h2>
            <p>国际通用的标准化筛查量表，几分钟即可完成。结果仅供参考，不能替代专业诊断。</p>
        </div>

        <div class="picker">
            <el-card v-for="s in scales" :key="s.code" class="pick-card"
                :class="{ active: currentCode === s.code }" shadow="hover" @click="chooseScale(s.code)">
                <h3>{{ s.name }}</h3>
                <p>{{ s.desc }}</p>
                <el-tag size="small" type="info">{{ s.count }} 题 · 约 {{ s.minutes }} 分钟</el-tag>
            </el-card>
        </div>

        <!-- ============ 答题 ============ -->
        <el-card v-if="questions.length" class="quiz-card">
            <template #header>
                <div class="quiz-head">
                    <span>{{ currentName }}</span>
                    <span class="progress">已答 {{ answeredCount }} / {{ questions.length }}</span>
                </div>
            </template>

            <p class="hint">请根据<strong>最近两周</strong>的实际情况作答：</p>

            <div v-for="(q, i) in questions" :key="i" class="question">
                <div class="q-title">{{ i + 1 }}. {{ q }}</div>
                <el-radio-group v-model="answers[i]">
                    <el-radio v-for="(opt, oi) in options" :key="oi" :value="oi" class="opt">
                        {{ opt }}
                    </el-radio>
                </el-radio-group>
            </div>

            <div class="actions">
                <el-button type="primary" size="large" :disabled="!allAnswered" :loading="submitting"
                    @click="handleSubmit">
                    提交并查看结果
                </el-button>
                <span v-if="!allAnswered" class="tip">还有 {{ questions.length - answeredCount }} 题未作答</span>
            </div>
        </el-card>

        <!-- ============ 结果 ============ -->
        <el-dialog v-model="resultVisible" title="测评结果" width="620px" :close-on-click-modal="false">
            <div v-if="result" class="result">
                <el-result :icon="result.selfHarmRisk ? 'warning' : 'success'">
                    <template #title>
                        <span class="score">{{ result.total }} <small>/ {{ result.maxTotal }}</small></span>
                    </template>
                    <template #sub-title>
                        <el-tag :type="levelTagType(result.level)" size="large">{{ result.level }}</el-tag>
                    </template>
                </el-result>

                <!-- ★ 自伤项命中：优先展示求助资源，不做任何淡化处理 -->
                <el-alert v-if="result.selfHarmRisk" type="error" :closable="false" class="crisis-alert">
                    <template #title>
                        <strong>你的回答中提到了一些很沉重的念头</strong>
                    </template>
                    <p>这值得被认真对待，你不必一个人扛着。下面这些渠道是免费且保密的，现在就可以联系：</p>
                    <ul class="hotlines">
                        <li v-for="line in CRISIS_HELPLINES" :key="line">{{ line }}</li>
                    </ul>
                </el-alert>

                <el-alert v-else type="info" :closable="false" class="disclaimer">
                    {{ result.disclaimer }}
                </el-alert>

                <div class="result-actions">
                    <el-button @click="resultVisible = false">知道了</el-button>
                    <el-button type="primary" @click="chooseScale(currentCode)">再测一次</el-button>
                </div>
            </div>
        </el-dialog>

        <!-- ============ 我的记录 ============ -->
        <el-card class="history-card">
            <template #header>
                <div class="quiz-head">
                    <span>我的测评记录</span>
                    <el-radio-group v-model="trendCode" size="small" @change="loadHistory">
                        <el-radio-button value="PHQ9">PHQ-9</el-radio-button>
                        <el-radio-button value="GAD7">GAD-7</el-radio-button>
                    </el-radio-group>
                </div>
            </template>

            <div v-if="history.length" ref="trendRef" class="trend-chart"></div>

            <el-table v-if="history.length" :data="history" style="width: 100%">
                <el-table-column prop="scaleName" label="量表" width="200" />
                <el-table-column prop="totalScore" label="总分" width="90" />
                <el-table-column label="程度" width="130">
                    <template #default="scope">
                        <el-tag :type="levelTagType(scope.row.level)" size="small">{{ scope.row.level }}</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="自伤项" width="100">
                    <template #default="scope">
                        <el-tag v-if="scope.row.selfHarmRisk" type="danger" size="small">需关注</el-tag>
                        <span v-else class="muted">—</span>
                    </template>
                </el-table-column>
                <el-table-column prop="createdAt" label="测评时间" />
            </el-table>

            <el-empty v-else description="还没有测评记录，选一个量表开始吧" />
        </el-card>
    </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { getMyScaleHistory, getScaleQuestions, getScaleTrend, submitScale } from '@/api/scale'
import { CRISIS_HELPLINES } from '@/utils/crisisResources'

const scales = [
    { code: 'PHQ9', name: 'PHQ-9 抑郁筛查', desc: '评估最近两周的抑郁情绪状态', count: 9, minutes: 2 },
    { code: 'GAD7', name: 'GAD-7 焦虑筛查', desc: '评估最近两周的焦虑水平', count: 7, minutes: 2 }
]

const currentCode = ref('PHQ9')
const currentName = ref('')
const questions = ref([])
const options = ref([])
const answers = ref([])
const submitting = ref(false)
const resultVisible = ref(false)
const result = ref(null)

const trendCode = ref('PHQ9')
const history = ref([])
const trendRef = ref(null)
let chart = null

const answeredCount = computed(() => answers.value.filter((a) => a !== undefined && a !== null).length)
const allAnswered = computed(() => questions.value.length > 0 && answeredCount.value === questions.value.length)

const levelTagType = (level) => {
    if (!level) return 'info'
    if (level.includes('重度')) return 'danger'
    if (level.includes('中度')) return 'warning'
    if (level.includes('轻度')) return 'success'
    return 'info'
}

const chooseScale = async (code) => {
    currentCode.value = code
    const res = await getScaleQuestions(code)
    questions.value = res.questions
    options.value = res.options
    currentName.value = res.name
    answers.value = new Array(res.questions.length).fill(null)
    resultVisible.value = false
    window.scrollTo({ top: 0, behavior: 'smooth' })
}

const handleSubmit = async () => {
    submitting.value = true
    try {
        const res = await submitScale(currentCode.value, answers.value)
        result.value = res
        resultVisible.value = true
        if (trendCode.value === currentCode.value) {
            await loadHistory()
        }
    } finally {
        submitting.value = false
    }
}

const loadHistory = async () => {
    const [rows, points] = await Promise.all([
        getMyScaleHistory(trendCode.value),
        getScaleTrend(trendCode.value)
    ])
    history.value = rows
    await nextTick()
    renderChart(points)
}

const renderChart = (points) => {
    if (!trendRef.value || !points.length) return
    if (!chart) {
        chart = echarts.init(trendRef.value)
    }
    const maxScore = trendCode.value === 'PHQ9' ? 27 : 21
    chart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 20, top: 30, bottom: 30 },
        xAxis: { type: 'category', data: points.map((p) => p.date) },
        yAxis: { type: 'value', max: maxScore, name: '总分' },
        series: [
            {
                name: '总分',
                type: 'line',
                smooth: true,
                data: points.map((p) => p.totalScore),
                areaStyle: { opacity: 0.15 },
                itemStyle: { color: '#ef4444' },
                markLine: {
                    silent: true,
                    data: [{ yAxis: 10, name: '中度界线' }],
                    lineStyle: { type: 'dashed', color: '#f59e0b' },
                    label: { formatter: '中度界线' }
                }
            }
        ]
    })
}

const onResize = () => chart && chart.resize()

// 切换量表类型时重画（数据点数量与上限都变了）
watch(trendCode, () => {
    if (chart) {
        chart.dispose()
        chart = null
    }
})

onMounted(() => {
    chooseScale('PHQ9')
    loadHistory()
    window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    if (chart) {
        chart.dispose()
        chart = null
    }
})
</script>

<style scoped>
.scale-page {
    max-width: 900px;
    margin: 0 auto;
    padding: 24px 16px 64px;
}

.intro h2 {
    margin-bottom: 8px;
    color: var(--nd-text-1);
}

.intro p {
    color: var(--nd-text-3);
    font-size: 14px;
}

.picker {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px;
    margin: 20px 0;
}

.pick-card {
    cursor: pointer;
    transition: all var(--nd-duration) var(--nd-ease);
}

.pick-card.active {
    border-color: var(--nd-primary-500);
    box-shadow: var(--nd-shadow-sm);
}

.pick-card h3 {
    margin-bottom: 6px;
    font-size: 16px;
    color: var(--nd-text-1);
}

.pick-card p {
    margin-bottom: 10px;
    font-size: 13px;
    color: var(--nd-text-3);
}

.quiz-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
}

.progress {
    font-size: 13px;
    color: var(--nd-text-3);
}

.hint {
    margin-bottom: 16px;
    color: var(--nd-text-3);
    font-size: 14px;
}

.question {
    padding: 14px 0;
    border-bottom: 1px solid var(--nd-border);
}

.q-title {
    margin-bottom: 10px;
    color: var(--nd-text-1);
    line-height: 1.6;
}

.opt {
    margin-right: 18px;
}

.actions {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 24px;
}

.tip {
    color: var(--nd-accent-600);
    font-size: 13px;
}

.result {
    text-align: center;
}

.score {
    font-size: 34px;
    font-weight: 700;
    color: var(--nd-text-1);
}

.score small {
    font-size: 15px;
    color: var(--nd-text-4);
}

.crisis-alert {
    text-align: left;
    margin-top: 10px;
}

.crisis-alert ul.hotlines {
    margin: 10px 0 0;
    padding-left: 18px;
    line-height: 1.9;
}

.disclaimer {
    text-align: left;
    margin-top: 10px;
}

.result-actions {
    margin-top: 18px;
    display: flex;
    gap: 10px;
    justify-content: center;
}

.history-card {
    margin-top: 24px;
}

.trend-chart {
    height: 260px;
    margin-bottom: 16px;
}

.muted {
    color: var(--nd-text-4);
}

@media (max-width: 640px) {
    .scale-page {
        padding: 16px 12px 48px;
    }
    /* 选项竖排，避免长文案被挤成一列字 */
    .opt {
        display: block;
        margin: 0 0 8px;
    }
    .result-actions {
        flex-direction: column;
    }
}
</style>
