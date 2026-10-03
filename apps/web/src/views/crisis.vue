<template>
    <div>
        <PageHead title="危机预警工单" subtitle="按风险等级排序，处置结果会留痕" />

        <!-- 待处理提醒：这是管理端最需要一眼看到的信息 -->
        <el-alert v-if="pendingCount > 0" type="error" :closable="false" class="pending-alert">
            <template #title>
                当前有 <strong>{{ pendingCount }}</strong> 条待处理的危机事件，建议优先跟进
            </template>
        </el-alert>

        <div class="toolbar">
            <el-checkbox v-model="onlyPending" @change="onTogglePending">只看待处理</el-checkbox>
            <el-button @click="showResources">查看求助资源</el-button>
        </div>

        <TableSearch :formItem="formItem" @search="handleSearch" />

        <!-- ⚠️ 列宽合计必须 ≤ 内容区宽度（桌面端约 1140px），否则 Element Plus
             会挤压各列导致日期换行成两截（真实出过：2026-10-02T… 被挤成两行）。
             当前合计：92+132+90+96+160+88+100+62+152+120 = 1092 ≤ 卡片内容区约 1100。加列要重算。 -->
        <el-table :data="tableData" style="width: 100%">
            <el-table-column label="风险等级" width="92">
                <template #default="scope">
                    <el-tag :type="levelType(scope.row.level)" effect="dark">
                        {{ levelText(scope.row.level) }}
                    </el-tag>
                </template>
            </el-table-column>
            <!-- ⚠️ 原来这一列根本没有，列表里只有「用户ID: 52」这种数字。
                 用户名/昵称本来就在接口里，取得到却没显示 —— 工单因此不可处置。 -->
            <el-table-column label="用户" width="132">
                <template #default="scope">
                    <div class="user-cell">
                        <span class="user-name">{{ displayName(scope.row) }}</span>
                        <span class="user-id">#{{ scope.row.userId }}</span>
                    </div>
                </template>
            </el-table-column>
            <el-table-column label="来源" width="90">
                <template #default="scope">{{ sourceText(scope.row.source) }}</template>
            </el-table-column>
            <el-table-column label="触发方式" width="96">
                <template #default="scope">
                    <el-tag size="small" :type="scope.row.triggerType === 'LLM' ? 'warning' : 'info'">
                        {{ scope.row.triggerType === 'LLM' ? '模型判定' : scope.row.triggerType === 'SCALE' ? '量表作答' : '关键词' }}
                    </el-tag>
                </template>
            </el-table-column>
            <el-table-column prop="contentSnippet" label="触发片段" min-width="160" show-overflow-tooltip />
            <el-table-column label="状态" width="88">
                <template #default="scope">
                    <el-tag :type="statusType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
                </template>
            </el-table-column>
            <!-- 处置人：不显示的话多人值班会重复联系同一个学生 -->
            <el-table-column label="处置人" width="100" show-overflow-tooltip>
                <template #default="scope">{{ scope.row.handlerName || '—' }}</template>
            </el-table-column>
            <el-table-column label="跟进" width="62">
                <template #default="scope">
                    <span v-if="scope.row.followUpCount" class="follow-badge">{{ scope.row.followUpCount }}</span>
                    <span v-else class="muted">—</span>
                </template>
            </el-table-column>
            <!-- 时间格式化成「2026-10-02 15:48」—— 原始 ISO 串又长又带 T，列里放不下 -->
            <el-table-column label="触发时间" width="152" show-overflow-tooltip>
                <template #default="scope">{{ shortTime(scope.row.createdAt) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
                <template #default="scope">
                    <el-button text type="primary" @click="openWorkbench(scope.row)">
                        {{ canHandle(scope.row.status) ? '处置' : '查看' }}
                    </el-button>
                </template>
            </el-table-column>
        </el-table>

        <el-pagination style="margin-top: 25px" :page-size="pagination.size" layout="prev, pager, next"
            :total="pagination.total" @change="handleChange" />

        <!-- ============ 处置工作台 ============ -->
        <el-dialog v-model="workbenchVisible" :title="workbenchTitle" width="1120px" top="4vh"
            :close-on-click-modal="false" class="workbench-dialog">
            <div v-loading="contextLoading">
                <el-alert v-if="current && current.level === 3" type="error" :closable="false" class="wb-alert">
                    <template #title>
                        3 级（危机）：请先阅读右侧处置清单，再决定是否立即联系 120/110 与辅导员。
                    </template>
                </el-alert>

                <div v-if="ctx" class="wb">
                    <!-- ---------- 左：这人是谁 ---------- -->
                    <section class="wb-col wb-left">
                        <h4 class="wb-title">这个人是谁</h4>
                        <el-descriptions :column="1" border size="small" class="wb-block">
                            <el-descriptions-item label="姓名">
                                {{ displayName(ctx.event) }}
                            </el-descriptions-item>
                            <el-descriptions-item label="账号">
                                {{ ctx.user?.username || '—' }}
                            </el-descriptions-item>
                            <el-descriptions-item label="注册时间">
                                {{ ctx.user?.createdAt || '—' }}
                            </el-descriptions-item>
                            <el-descriptions-item label="账号状态">
                                <el-tag size="small" :type="ctx.user?.status === 1 ? 'success' : 'danger'">
                                    {{ ctx.user?.status === 1 ? '正常' : '已禁用' }}
                                </el-tag>
                            </el-descriptions-item>
                            <el-descriptions-item label="日记 / 会话 / 工单">
                                {{ ctx.user?.diaryCount ?? 0 }} / {{ ctx.user?.sessionCount ?? 0 }} /
                                <strong>{{ ctx.user?.crisisCount ?? 0 }}</strong>
                            </el-descriptions-item>
                        </el-descriptions>

                        <h4 class="wb-title">
                            历史工单
                            <el-tag v-if="ctx.history.length" size="small" type="danger">
                                复发 {{ ctx.history.length }} 次
                            </el-tag>
                            <el-tag v-else size="small" type="info">首次</el-tag>
                        </h4>
                        <div v-if="!ctx.history.length" class="wb-empty">此前没有产生过危机事件</div>
                        <ul v-else class="history-list">
                            <li v-for="h in ctx.history" :key="h.id">
                                <div class="history-head">
                                    <el-tag size="small" :type="levelType(h.level)" effect="dark">
                                        {{ levelText(h.level) }}
                                    </el-tag>
                                    <span class="muted">{{ h.createdAt }}</span>
                                    <el-tag size="small" :type="statusType(h.status)">{{ statusText(h.status) }}</el-tag>
                                </div>
                                <div class="history-snippet">{{ h.contentSnippet || '—' }}</div>
                                <div v-if="h.handleNote" class="history-note">处置：{{ h.handleNote }}</div>
                            </li>
                        </ul>

                        <template v-if="ctx.scales.length">
                            <h4 class="wb-title">心理量表</h4>
                            <ul class="mini-list">
                                <li v-for="s in ctx.scales" :key="s.id">
                                    <span>{{ s.scaleName || s.scaleCode }}</span>
                                    <span>{{ s.totalScore }} 分 · {{ s.level }}</span>
                                    <!-- ⚠️ 自伤项要单独看：有分就说明有风险，与总分高低无关 -->
                                    <el-tag v-if="s.selfHarmScore" size="small" type="danger">
                                        自伤项 {{ s.selfHarmScore }}
                                    </el-tag>
                                </li>
                            </ul>
                        </template>

                        <template v-if="ctx.diaries.length">
                            <h4 class="wb-title">
                                近期日记趋势
                                <el-tag v-if="ctx.diaryTrend.lowDays" size="small" type="warning">
                                    连续低分 {{ ctx.diaryTrend.lowDays }} 天
                                </el-tag>
                            </h4>
                            <div class="trend-row">
                                <span>近 {{ ctx.diaryTrend.count }} 篇</span>
                                <span>平均心情 {{ ctx.diaryTrend.avgMood ?? '—' }}</span>
                                <span>最低 {{ ctx.diaryTrend.minMood ?? '—' }}</span>
                            </div>
                            <ul class="mini-list">
                                <li v-for="d in ctx.diaries.slice(0, 5)" :key="d.id">
                                    <span class="muted">{{ d.diaryDate }}</span>
                                    <span>心情 {{ d.moodScore }} · {{ d.dominantEmotion || '—' }}</span>
                                </li>
                            </ul>
                        </template>
                    </section>

                    <!-- ---------- 中：发生了什么 ---------- -->
                    <section class="wb-col wb-mid">
                        <h4 class="wb-title">
                            触发原文
                            <el-tag size="small">{{ sourceText(ctx.source?.source) }}</el-tag>
                            <el-button text type="primary" size="small" @click="openUserSessions">
                                查看该用户全部会话
                            </el-button>
                        </h4>

                        <!-- 对话来源：完整上下文，不截断 -->
                        <template v-if="ctx.source?.source === 'CHAT'">
                            <div class="wb-subtitle">会话：{{ ctx.source.sessionTitle || '—' }}（#{{ ctx.source.sessionId }}）</div>
                            <div class="chat-box">
                                <div v-for="m in ctx.source.messages" :key="m.id" class="chat-item"
                                    :class="[m.senderType === 1 ? 'is-user' : 'is-ai', { 'is-trigger': m.id === ctx.source.triggerMessageId }]">
                                    <div class="chat-head">
                                        <span class="sender">{{ m.senderTypeDesc || (m.senderType === 1 ? '用户' : 'AI助手') }}</span>
                                        <span class="muted">{{ m.createdAt }}</span>
                                        <el-tag v-if="m.id === ctx.source.triggerMessageId" size="small" type="danger">
                                            触发点
                                        </el-tag>
                                    </div>
                                    <div class="chat-content">{{ m.content }}</div>
                                </div>
                                <div v-if="!ctx.source.messages.length" class="wb-empty">（该会话消息已删除）</div>
                            </div>
                        </template>

                        <!-- 日记来源 -->
                        <template v-else-if="ctx.source?.diary">
                            <div class="wb-subtitle">
                                日记日期 {{ ctx.source.diary.diaryDate }} · 心情 {{ ctx.source.diary.moodScore }} ·
                                {{ ctx.source.diary.dominantEmotion || '—' }}
                            </div>
                            <div class="diary-box">{{ ctx.source.diary.content }}</div>
                        </template>

                        <div v-else class="wb-empty">（未关联到原始记录，可能来源为量表作答）</div>

                        <h4 class="wb-title">命中内容</h4>
                        <div class="wb-subtitle">
                            {{ ctx.event.matchedTerms || '—' }}（{{ ctx.event.triggerType === 'LLM' ? '模型判定' : '关键词' }}）
                        </div>
                    </section>

                    <!-- ---------- 右：我该做什么 ---------- -->
                    <section class="wb-col wb-right">
                        <h4 class="wb-title">处置清单</h4>
                        <ol class="checklist">
                            <li v-for="(step, i) in ctx.checklist" :key="i">{{ step }}</li>
                        </ol>

                        <template v-if="canHandle(ctx.event.status)">
                            <h4 class="wb-title">已采取措施</h4>
                            <el-checkbox-group v-model="handleForm.measures" class="measure-group">
                                <el-checkbox v-for="m in ctx.measureOptions" :key="m.code" :value="m.code">
                                    {{ m.label }}
                                </el-checkbox>
                            </el-checkbox-group>

                            <h4 class="wb-title">处置结果</h4>
                            <el-radio-group v-model="handleForm.status">
                                <el-radio value="RESOLVED">已处置</el-radio>
                                <el-radio value="HANDLING">处理中</el-radio>
                                <el-radio value="IGNORED">误报忽略</el-radio>
                            </el-radio-group>

                            <el-input v-model="handleForm.handleNote" type="textarea" :rows="3" class="wb-note"
                                placeholder="例如：已电话联系该生，情绪平稳，已告知辅导员" />

                            <el-button type="primary" class="wb-submit" :loading="submitting" @click="submitHandle">
                                提交处置
                            </el-button>
                        </template>

                        <template v-else>
                            <h4 class="wb-title">处置结果</h4>
                            <div class="result-line">
                                <el-tag :type="statusType(ctx.event.status)" size="small">
                                    {{ statusText(ctx.event.status) }}
                                </el-tag>
                                <span class="muted">{{ ctx.event.handledAt || '' }}</span>
                            </div>
                            <div class="result-line">处置人：{{ ctx.event.handlerName || '—' }}</div>
                            <div v-if="ctx.event.measures.length" class="measure-tags">
                                <el-tag v-for="code in ctx.event.measures" :key="code" size="small">
                                    {{ measureLabel(code) }}
                                </el-tag>
                            </div>
                            <div v-if="ctx.event.handleNote" class="result-note">{{ ctx.event.handleNote }}</div>
                        </template>

                        <!-- 跟进：处置不是一次性的 -->
                        <h4 class="wb-title">跟进记录（{{ ctx.followUps.length }}）</h4>
                        <ul v-if="ctx.followUps.length" class="follow-list">
                            <li v-for="f in ctx.followUps" :key="f.id">
                                <div class="follow-head">
                                    <span>{{ f.operatorName || '未知' }}</span>
                                    <span class="muted">{{ f.createdAt }}</span>
                                </div>
                                <div class="follow-content">{{ f.content }}</div>
                            </li>
                        </ul>
                        <div v-else class="wb-empty">还没有跟进记录</div>
                        <el-input v-model="followUpText" type="textarea" :rows="2" maxlength="2000" show-word-limit
                            placeholder="追加一条跟进，例如：3 天后复查，情绪平稳" />
                        <el-button class="wb-submit" :loading="followSubmitting" :disabled="!followUpText.trim()"
                            @click="submitFollowUp">
                            追加跟进
                        </el-button>
                    </section>
                </div>
            </div>
        </el-dialog>

        <!-- ============ 求助资源 ============ -->
        <el-dialog v-model="resourcesVisible" title="危机求助资源" width="560px">
            <div v-if="resources">
                <h4>{{ resources.title }}</h4>
                <p class="subtitle">{{ resources.subtitle }}</p>
                <ul class="hotlines">
                    <li v-for="(h, i) in resources.helplines" :key="i">{{ h }}</li>
                </ul>
                <p class="disclaimer">{{ resources.disclaimer }}</p>
            </div>
        </el-dialog>
    </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHead from '@/components/PageHead.vue'
import TableSearch from '@/components/TableSearch.vue'
import {
    getCrisisPage,
    getCrisisPendingCount,
    getCrisisResources,
    getCrisisContext,
    addCrisisFollowUp,
    handleCrisisEvent
} from '@/api/admin'

const router = useRouter()
const route = useRoute()

const formItem = [
    // 支持从咨询记录「工单 N」带 keyword 跳进来（按账号/昵称过滤）
    { prop: 'keyword', label: '用户', comp: 'input', placeholder: '账号或昵称' },
    {
        prop: 'status', label: '处置状态', comp: 'select', placeholder: '全部',
        options: [
            { label: '待处理', value: 'PENDING' },
            { label: '处理中', value: 'HANDLING' },
            { label: '已处置', value: 'RESOLVED' },
            { label: '已忽略', value: 'IGNORED' }
        ]
    },
    {
        prop: 'level', label: '风险等级', comp: 'select', placeholder: '全部',
        options: [
            { label: '关注', value: 1 },
            { label: '预警', value: 2 },
            { label: '危机', value: 3 }
        ]
    }
]

const tableData = ref([])
const pagination = ref({ currentPage: 1, size: 10, total: 0 })
const pendingCount = ref(0)
const filters = ref({})
const onlyPending = ref(false)
// 从咨询记录跳过来时带上用户名，直接筛出该用户的工单
const initialKeyword = route.query.keyword || ''

const workbenchVisible = ref(false)
const resourcesVisible = ref(false)
const current = ref(null)
const ctx = ref(null)
const contextLoading = ref(false)
const submitting = ref(false)
const followSubmitting = ref(false)
const followUpText = ref('')
const handleForm = ref({ status: 'RESOLVED', handleNote: '', measures: [] })
const resources = ref(null)

const LEVELS = { 1: '关注', 2: '预警', 3: '危机' }
const levelText = (lv) => LEVELS[lv] || '未知'
const levelType = (lv) => ({ 1: 'info', 2: 'warning', 3: 'danger' }[lv] || 'info')
const sourceText = (s) => ({ CHAT: '咨询对话', DIARY: '情绪日记', SCALE: '心理量表' }[s] || s || '未知')
const statusText = (s) =>
    ({ PENDING: '待处理', HANDLING: '处理中', RESOLVED: '已处置', IGNORED: '已忽略' }[s] || s)
const statusType = (s) =>
    ({ PENDING: 'danger', HANDLING: 'warning', RESOLVED: 'success', IGNORED: 'info' }[s] || 'info')
const canHandle = (s) => s === 'PENDING' || s === 'HANDLING'

// 列表里的「用户」列：昵称优先，没有就退回账号。
// 后端两个字段都给了，这里只做展示兜底 —— 千万别再只读一个不存在的字段。
const displayName = (row) => row?.nickname || row?.username || `用户 #${row?.userId ?? '—'}`

/** ISO 时间 → 「2026-10-02 15:48」。后端给的是 "2026-10-02T15:48:26"，
 *  原始串带 T 且到秒，列里放不下会折行（真实踩过）。解析失败原样返回。 */
const shortTime = (iso) => {
    if (!iso || typeof iso !== 'string') return '—'
    const s = iso.slice(0, 16).replace('T', ' ')
    return s || '—'
}

const measureLabel = (code) => {
    const found = ctx.value?.measureOptions?.find((m) => m.code === code)
    // 已处置工单的措施可能不在当前等级的选项里（例如 1 级工单勾了「已通知家长」），
    // 这时至少把编码显示出来，而不是空白。
    return found ? found.label : code
}

const workbenchTitle = computed(() => {
    if (!current.value) return '处置工作台'
    return `${levelText(current.value.level)}级 · ${displayName(current.value)} · #${current.value.id}`
})

const loadData = async () => {
    const params = {
        currentPage: pagination.value.currentPage,
        size: pagination.value.size,
        ...filters.value
    }
    // 空字符串会被后端当成有效筛选值，清掉
    Object.keys(params).forEach((k) => {
        if (params[k] === '' || params[k] === null || params[k] === undefined) delete params[k]
    })

    const res = await getCrisisPage(params)
    tableData.value = res.records
    pagination.value.total = res.total
}

const loadPending = async () => {
    pendingCount.value = await getCrisisPendingCount()
}

const handleSearch = (form) => {
    filters.value = { ...form }
    pagination.value.currentPage = 1
    loadData()
}

const handleChange = (page) => {
    pagination.value.currentPage = page
    loadData()
}

const onTogglePending = (val) => {
    filters.value = val ? { status: 'PENDING', ...filters.value } : { ...filters.value }
    if (!val) delete filters.value.status
    pagination.value.currentPage = 1
    loadData()
}

const openWorkbench = async (row) => {
    current.value = row
    ctx.value = null
    handleForm.value = { status: 'RESOLVED', handleNote: '', measures: [] }
    followUpText.value = ''
    workbenchVisible.value = true

    contextLoading.value = true
    try {
        ctx.value = await getCrisisContext(row.id)
    } finally {
        contextLoading.value = false
    }
}

const submitHandle = async () => {
    submitting.value = true
    try {
        await handleCrisisEvent(current.value.id, handleForm.value)
        ElMessage.success('已提交处置结果')
        await refreshWorkbench()
        await Promise.all([loadData(), loadPending()])
    } finally {
        submitting.value = false
    }
}

const submitFollowUp = async () => {
    followSubmitting.value = true
    try {
        await addCrisisFollowUp(current.value.id, followUpText.value.trim())
        followUpText.value = ''
        ElMessage.success('已追加跟进')
        await refreshWorkbench()
        await loadData()
    } finally {
        followSubmitting.value = false
    }
}

const refreshWorkbench = async () => {
    ctx.value = await getCrisisContext(current.value.id)
}

/** 跳到咨询记录并自动按该用户检索 —— 工单与原始记录之间原本没有这条通路 */
const openUserSessions = () => {
    const row = ctx.value?.event
    if (!row) return
    router.push({
        path: '/back/consultations',
        query: { keyword: row.username || row.nickname || '' }
    })
}

const showResources = async () => {
    if (!resources.value) {
        resources.value = await getCrisisResources()
    }
    resourcesVisible.value = true
}

onMounted(() => {
    if (initialKeyword) filters.value = { keyword: initialKeyword }
    loadData()
    loadPending()
})
</script>

<style scoped>
.pending-alert {
    margin-bottom: 16px;
}

.toolbar {
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 16px;
}

.user-cell {
    display: flex;
    flex-direction: column;
    line-height: 1.35;
}

.user-name {
    font-weight: 500;
    color: var(--nd-text-1);
}

.user-id {
    font-size: 12px;
    color: var(--nd-text-4);
}

.follow-badge {
    display: inline-block;
    min-width: 20px;
    padding: 0 6px;
    border-radius: 10px;
    background: var(--nd-primary-100);
    color: var(--nd-primary-700);
    font-size: 12px;
    text-align: center;
}

.muted {
    color: var(--nd-text-4);
    font-size: 12px;
}

/* ===== 处置工作台 ===== */
.wb-alert {
    margin-bottom: 14px;
}

.wb {
    display: grid;
    grid-template-columns: 280px 1fr 320px;
    gap: 18px;
    align-items: start;
}

.wb-col {
    max-height: 66vh;
    overflow-y: auto;
    padding-right: 4px;
}

.wb-left,
.wb-right {
    background: var(--nd-surface-soft);
    border: 1px solid var(--nd-border);
    border-radius: 10px;
    padding: 14px;
}

.wb-title {
    margin: 0 0 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--nd-text-1);
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
}

.wb-col .wb-title:not(:first-child) {
    margin-top: 18px;
}

.wb-block {
    margin-bottom: 4px;
}

.wb-subtitle {
    font-size: 12px;
    color: var(--nd-text-3);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.wb-empty {
    font-size: 13px;
    color: var(--nd-text-4);
    padding: 10px 0;
}

.history-list,
.mini-list,
.follow-list {
    list-style: none;
    margin: 0;
    padding: 0;
}

.history-list li {
    border: 1px solid var(--nd-border);
    border-radius: 8px;
    padding: 10px;
    margin-bottom: 8px;
    background: #fff;
}

.history-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    flex-wrap: wrap;
}

.history-snippet {
    font-size: 13px;
    color: var(--nd-text-2);
    line-height: 1.6;
}

.history-note {
    margin-top: 6px;
    font-size: 12px;
    color: var(--nd-text-3);
}

.mini-list li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    padding: 6px 0;
    border-bottom: 1px dashed var(--nd-border);
    color: var(--nd-text-2);
}

.trend-row {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: var(--nd-text-3);
    margin-bottom: 6px;
}

/* 触发原文 */
.chat-box {
    border: 1px solid var(--nd-border);
    border-radius: 8px;
    background: #fff;
    padding: 12px;
    max-height: 46vh;
    overflow-y: auto;
}

.chat-item {
    padding: 10px;
    border-radius: 8px;
    margin-bottom: 10px;
    background: var(--nd-surface-soft);
    border: 1px solid transparent;
}

.chat-item.is-user {
    background: var(--nd-info-bg);
}

.chat-item.is-ai {
    background: var(--nd-success-bg);
}

.chat-item.is-trigger {
    border-color: var(--nd-danger);
    background: var(--nd-danger-bg);
}

.chat-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
}

.chat-head .sender {
    font-weight: 500;
    font-size: 13px;
    color: var(--nd-text-1);
}

.chat-content {
    font-size: 13px;
    line-height: 1.7;
    white-space: pre-wrap;
    color: var(--nd-text-1);
}

.diary-box {
    border: 1px solid var(--nd-border);
    border-radius: 8px;
    background: #fff;
    padding: 12px;
    font-size: 13px;
    line-height: 1.7;
    white-space: pre-wrap;
    max-height: 46vh;
    overflow-y: auto;
}

/* 处置 */
.checklist {
    margin: 0;
    padding-left: 20px;
    font-size: 13px;
    line-height: 1.8;
    color: var(--nd-text-2);
}

.measure-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.wb-note {
    margin-top: 10px;
}

.wb-submit {
    width: 100%;
    margin-top: 10px;
}

.result-line {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--nd-text-2);
    margin-bottom: 6px;
}

.result-note {
    font-size: 13px;
    color: var(--nd-text-2);
    line-height: 1.6;
}

.measure-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 8px;
}

.follow-list li {
    border-top: 1px dashed var(--nd-border);
    padding: 8px 0;
}

.follow-head {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--nd-text-3);
    margin-bottom: 4px;
}

.follow-content {
    font-size: 13px;
    line-height: 1.6;
    color: var(--nd-text-1);
    white-space: pre-wrap;
}

.subtitle {
    color: var(--nd-text-3);
    font-size: 13px;
    margin: 6px 0 10px;
}

.hotlines {
    line-height: 2;
    padding-left: 20px;
}

.disclaimer {
    margin-top: 12px;
    font-size: 12px;
    color: var(--nd-text-4);
    line-height: 1.7;
}
</style>
