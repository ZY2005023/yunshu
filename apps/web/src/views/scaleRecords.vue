<template>
    <div>
        <PageHead title="量表测评记录" subtitle="可筛选自伤项命中的记录，优先跟进" />

        <el-alert type="info" :closable="false" class="intro-alert">
            这里可以看到所有用户的 PHQ-9 / GAD-7 测评结果。
            <strong>「自伤项」标记为需关注的记录建议优先跟进</strong> —— 那说明用户在 PHQ-9 第 9 题
            （自伤念头）上有得分，与总分高低无关。
        </el-alert>

        <TableSearch :formItem="formItem" @search="handleSearch" />

        <el-table :data="tableData" style="width: 100%">
            <el-table-column label="用户" width="180">
                <template #default="scope">
                    <div class="user-cell">
                        <el-avatar :size="28">{{ (scope.row.nickname || scope.row.username || '?').charAt(0) }}</el-avatar>
                        <span>{{ scope.row.nickname || scope.row.username || '-' }}</span>
                    </div>
                </template>
            </el-table-column>
            <el-table-column prop="scaleName" label="量表" width="200" />
            <el-table-column label="总分" width="110">
                <template #default="scope">
                    <strong>{{ scope.row.totalScore }}</strong>
                    <span class="muted"> / {{ scope.row.scaleCode === 'PHQ9' ? 27 : 21 }}</span>
                </template>
            </el-table-column>
            <el-table-column label="程度" width="130">
                <template #default="scope">
                    <el-tag :type="levelType(scope.row.level)" size="small">{{ scope.row.level }}</el-tag>
                </template>
            </el-table-column>
            <el-table-column label="自伤项" width="110">
                <template #default="scope">
                    <el-tag v-if="scope.row.selfHarmRisk" type="danger" size="small" effect="dark">
                        需关注
                    </el-tag>
                    <span v-else class="muted">—</span>
                </template>
            </el-table-column>
            <el-table-column prop="createdAt" label="测评时间" width="180" />
            <el-table-column label="操作" width="180" fixed="right">
                <template #default="scope">
                    <el-button text type="primary" @click="viewDetail(scope.row)">详情</el-button>
                    <!-- 与咨询记录页同一条通路：量表 ↔ 危机工单此前没有互跳 -->
                    <el-button text type="warning" @click="openTickets(scope.row)">查工单</el-button>
                </template>
            </el-table-column>
        </el-table>

        <el-pagination style="margin-top: 25px" :page-size="pagination.size" layout="prev, pager, next"
            :total="pagination.total" @change="handleChange" />

        <el-dialog v-model="detailVisible" title="测评详情" width="560px">
            <el-descriptions v-if="current" :column="1" border>
                <el-descriptions-item label="用户">
                    {{ current.nickname || current.username }}（ID {{ current.userId }}）
                </el-descriptions-item>
                <el-descriptions-item label="量表">{{ current.scaleName }}</el-descriptions-item>
                <el-descriptions-item label="总分">
                    {{ current.totalScore }} / {{ current.scaleCode === 'PHQ9' ? 27 : 21 }}
                </el-descriptions-item>
                <el-descriptions-item label="程度">
                    <el-tag :type="levelType(current.level)">{{ current.level }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="自伤项">
                    <el-tag v-if="current.selfHarmRisk" type="danger" effect="dark">有得分，建议跟进</el-tag>
                    <span v-else>无</span>
                </el-descriptions-item>
                <el-descriptions-item label="测评时间">{{ current.createdAt }}</el-descriptions-item>
            </el-descriptions>

            <el-alert v-if="current && current.selfHarmRisk" type="warning" :closable="false" class="tip-alert">
                该用户在 PHQ-9 第 9 题（自伤念头）上有得分。建议结合咨询记录与情绪日志综合评估，
                必要时联系辅导员或校心理中心。
            </el-alert>
        </el-dialog>
    </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import TableSearch from '@/components/TableSearch.vue'
import { getScaleRecordPage } from '@/api/admin'

const router = useRouter()

/** 跳到危机工单并自动按该用户检索 —— 自伤项命中的记录恰恰最需要跟进 */
const openTickets = (row) => {
    router.push({
        path: '/back/crisis',
        query: { keyword: row.username || row.nickname || '' }
    })
}

const formItem = [
    {
        prop: 'code', label: '量表', comp: 'select', placeholder: '全部',
        options: [
            { label: 'PHQ-9 抑郁筛查', value: 'PHQ9' },
            { label: 'GAD-7 焦虑筛查', value: 'GAD7' }
        ]
    },
    {
        prop: 'onlySelfHarm', label: '自伤项', comp: 'select', placeholder: '全部',
        options: [
            { label: '仅看需关注', value: true },
            { label: '不含自伤', value: false }
        ]
    }
]

const tableData = ref([])
const pagination = ref({ currentPage: 1, size: 10, total: 0 })
const filters = ref({})
const detailVisible = ref(false)
const current = ref(null)

const levelType = (level) => {
    if (!level) return 'info'
    if (level.includes('重度')) return 'danger'
    if (level.includes('中度')) return 'warning'
    if (level.includes('轻度')) return 'success'
    return 'info'
}

const loadData = async () => {
    const params = {
        currentPage: pagination.value.currentPage,
        size: pagination.value.size,
        ...filters.value
    }
    Object.keys(params).forEach((k) => {
        if (params[k] === '' || params[k] === null || params[k] === undefined) delete params[k]
    })

    const res = await getScaleRecordPage(params)
    tableData.value = res.records
    pagination.value.total = res.total
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

const viewDetail = (row) => {
    current.value = row
    detailVisible.value = true
}

onMounted(loadData)
</script>

<style scoped>
.intro-alert {
    margin-bottom: 16px;
}

.user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
}

.muted {
    color: var(--nd-text-4);
}

.tip-alert {
    margin-top: 14px;
    line-height: 1.8;
}
</style>
