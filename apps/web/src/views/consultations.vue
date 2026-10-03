<template>
    <div>
        <PageHead title="咨询记录" subtitle="可按关键词检索，支持按风险排序" />

        <div class="toolbar">
            <!-- 默认「风险优先」：有危机事件的会话排在最前。
                 否则老师要在成百上千条日常闲聊里翻出需要关注的那几条。 -->
            <el-checkbox v-model="riskFirst" @change="handleSearch">风险优先排序</el-checkbox>
            <span class="toolbar-hint">
                共 {{ pagination.total }} 条会话
                <template v-if="riskCount">，其中 {{ riskCount }} 条产生过危机事件</template>
            </span>
        </div>

        <TableSearch :formItem="formItem" @search="onSearch" />

        <el-table :data="tableData" style="width: 100%">
            <!-- ⚠️ 原来这一列叫「会话ID」却放了个头像，而且读的是不存在的 userNickname
                 → 头像恒空白。后端给的是 nickname / username。 -->
            <el-table-column label="用户" width="140">
                <template #default="scope">
                    <div class="user-cell">
                        <el-avatar :size="28">{{ (scope.row.nickname || scope.row.username || '?').slice(0, 1) }}</el-avatar>
                        <div class="user-text">
                            <span class="user-name">{{ scope.row.nickname || scope.row.username || '未知用户' }}</span>
                            <span class="user-sub">@{{ scope.row.username || '—' }}</span>
                        </div>
                    </div>
                </template>
            </el-table-column>
            <!-- ⚠️ 原来列名叫「情绪日志」，里面放的却是会话标题 -->
            <el-table-column label="会话" min-width="220">
                <template #default="scope">
                    <div class="session-title">{{ scope.row.sessionTitle || '（无标题）' }}</div>
                    <div class="session-preview">{{ scope.row.lastMessageContent || '暂无消息' }}</div>
                </template>
            </el-table-column>
            <el-table-column prop="messageCount" label="消息数" width="90" />
            <el-table-column label="时长" width="90">
                <template #default="scope">{{ scope.row.durationMinutes }} 分钟</template>
            </el-table-column>
            <!-- ⚠️ 原来 prop 是 lastMessageTime（接口根本没有这个字段）→ 整列空白。
                 接口返回的是 startedAt。 -->
            <el-table-column prop="startedAt" label="开始时间" width="170" />
            <el-table-column label="风险" width="100">
                <template #default="scope">
                    <el-tag v-if="scope.row.riskLevel" :type="levelType(scope.row.riskLevel)" effect="dark" size="small">
                        {{ levelText(scope.row.riskLevel) }}
                    </el-tag>
                    <span v-else class="muted">—</span>
                </template>
            </el-table-column>
            <el-table-column label="操作" width="160" fixed="right">
                <template #default="scope">
                    <div class="ops">
                        <el-button type="primary" text @click="viewSessionDetail(scope.row)">详情</el-button>
                        <el-button v-if="scope.row.crisisCount" text type="danger"
                            @click="openUserTickets(scope.row)">
                            工单 {{ scope.row.crisisCount }}
                        </el-button>
                    </div>
                </template>
            </el-table-column>
        </el-table>

        <el-pagination style="margin-top: 25px" :page-size="pagination.size" layout="prev, pager, next"
            :total="pagination.total" @change="handleChange" />

        <el-dialog v-model="showDetailDialog" title="咨询会话详情" width="70%" :close-on-click-modal="false">
            <div class="session-detail">
                <el-alert v-if="sessionDetail.riskLevel" type="error" :closable="false" class="detail-alert">
                    <template #title>
                        该会话触发过 <strong>{{ levelText(sessionDetail.riskLevel) }}</strong> 级危机事件（{{
                            sessionDetail.crisisCount }} 条）
                    </template>
                </el-alert>
                <div class="detail-header">
                    <div class="detail-row">
                        <div class="detail-label">用户：</div>
                        <div class="detail-value">
                            {{ sessionDetail.nickname || sessionDetail.username || '未知用户' }}
                            <span class="muted">@{{ sessionDetail.username || '—' }}</span>
                        </div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">开始时间：</div>
                        <div class="detail-value">{{ sessionDetail.startedAt }}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">消息数：</div>
                        <div class="detail-value">{{ sessionDetail.messageCount }}</div>
                    </div>
                    <div class="detail-row">
                        <div class="detail-label">时长：</div>
                        <div class="detail-value">{{ sessionDetail.durationMinutes }} 分钟</div>
                    </div>
                </div>
                <div class="messages-container">
                    <div class="messages-header">
                        <h4>对话记录</h4>
                        <el-button v-if="sessionDetail.crisisCount" text type="danger" size="small"
                            @click="openUserTickets(sessionDetail)">
                            查看该用户工单
                        </el-button>
                    </div>
                    <div class="messages-list" v-loading="loadingMessages">
                        <div v-for="message in sessionMessages" :key="message.id" class="message-item"
                            :class="message.senderType === 1 ? 'user-message' : 'ai-message'">
                            <div class="message-header">
                                <span class="sender">{{ message.senderType === 1 ? '用户' : 'AI助手' }}</span>
                                <span class="time">{{ message.createdAt }}</span>
                            </div>
                            <div class="message-content">{{ message.content }}</div>
                        </div>
                        <div v-if="!loadingMessages && !sessionMessages.length" class="wb-empty">该会话没有消息</div>
                    </div>
                </div>
            </div>
            <template #footer>
                <el-button @click="showDetailDialog = false">关闭</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHead from '@/components/PageHead.vue'
import TableSearch from '@/components/TableSearch.vue'
import { getConsultationPage, getSessionDetail } from '@/api/admin'

const route = useRoute()
const router = useRouter()

const tableData = ref([])
const riskCount = ref(0)

const pagination = reactive({
    currentPage: 1,
    size: 10,
    total: 0
})

const riskFirst = ref(true)
// 支持从危机工单「查看该用户全部会话」带 keyword 跳进来
const keyword = ref(route.query.keyword || '')
const riskOnly = ref(false)

const formItem = [
    { prop: 'keyword', label: '关键词', comp: 'input', placeholder: '会话标题 / 用户名 / 消息内容' },
    {
        prop: 'riskOnly', label: '有无风险', comp: 'select', placeholder: '全部',
        options: [{ label: '仅看有风险的', value: true }]
    }
]

const showDetailDialog = ref(false)
const sessionDetail = ref({})
const sessionMessages = ref([])
const loadingMessages = ref(false)

const levelText = (lv) => ({ 1: '关注', 2: '预警', 3: '危机' }[lv] || '未知')
const levelType = (lv) => ({ 1: 'info', 2: 'warning', 3: 'danger' }[lv] || 'info')

const handleSearch = () => {
    const params = {
        currentPage: pagination.currentPage,
        size: pagination.size,
        riskFirst: riskFirst.value,
        riskOnly: riskOnly.value || undefined,
        keyword: keyword.value || undefined
    }
    getConsultationPage(params).then((res) => {
        const { records, total } = res
        tableData.value = records
        pagination.total = total
        // 有风险的会话数（当前筛选条件下），给老师一个量级概念
        riskCount.value = records.filter((r) => r.riskLevel).length
    })
}

const onSearch = (form) => {
    keyword.value = form.keyword || ''
    riskOnly.value = form.riskOnly ?? false
    pagination.currentPage = 1
    handleSearch()
}

const handleChange = (page) => {
    pagination.currentPage = page
    handleSearch()
}

const viewSessionDetail = (row) => {
    loadingMessages.value = true
    showDetailDialog.value = true
    sessionDetail.value = row
    sessionMessages.value = []
    getSessionDetail(row.id)
        .then((res) => {
            // 接口返回 { sessionId, messages } —— **不能直接把对象当数组遍历**
            sessionMessages.value = Array.isArray(res) ? res : (res?.messages || [])
        })
        .finally(() => {
            loadingMessages.value = false
        })
}

/** 跳到危机工单并自动按该用户检索 —— 两个模块之间原本没有这条通路 */
const openUserTickets = (row) => {
    router.push({
        path: '/back/crisis',
        query: { keyword: row.username || row.nickname || '' }
    })
}

onMounted(() => {
    handleSearch()
})
</script>

<style lang="scss" scoped>
.toolbar {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 12px;
}

.toolbar-hint {
    font-size: 12px;
    color: var(--nd-text-4);
}

.muted {
    color: var(--nd-text-4);
    font-size: 12px;
}

.wb-empty {
    padding: 16px 0;
    text-align: center;
    font-size: 13px;
    color: var(--nd-text-4);
}

.user-cell {
    display: flex;
    align-items: center;
    gap: 8px;
}

.user-text {
    display: flex;
    flex-direction: column;
    line-height: 1.3;
    overflow: hidden;
}

.user-name {
    font-weight: 500;
    color: var(--nd-text-1);
    font-size: 13px;
}

.user-sub {
    font-size: 11px;
    color: var(--nd-text-4);
}

.session-title {
    font-weight: 500;
    color: var(--nd-text-1);
    margin-bottom: 4px;
}

.session-preview {
    font-size: 13px;
    color: var(--nd-text-2);
    margin-bottom: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.ops {
    display: flex;
    white-space: nowrap;
    align-items: center;
}

.session-detail {
    max-height: 70vh;
    overflow-y: auto;

    .detail-alert {
        margin-bottom: 14px;
    }

    .detail-header {
        margin-bottom: 20px;
        padding: 16px;
        background: var(--nd-surface-soft);
        border-radius: 8px;
        border: 1px solid var(--nd-border);
    }

    .detail-row {
        display: flex;
        align-items: center;
        margin-bottom: 8px;

        :last-child {
            margin-bottom: 0;
        }

        .detail-label {
            font-weight: 500;
            color: var(--nd-text-2);
            min-width: 80px;
            margin-right: 8px;
        }

        .detail-value {
            color: var(--nd-text-1);
        }
    }
}

.messages-container {
    margin-top: 20px;

    .messages-header {
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;

        h4 {
            margin: 0;
            color: var(--nd-text-1);
            font-size: 16px;
            font-weight: 500;
        }
    }

    .messages-list {
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid var(--nd-border);
        border-radius: 8px;
        padding: 16px;
        background: #fff;

        .message-item {
            margin-bottom: 12px;
            padding: 12px;
            border-radius: 8px;
            background: var(--nd-surface-soft);
            border: 1px solid var(--nd-border);

            :last-child {
                margin-bottom: 0;
            }

            &.user-message {
                background: var(--nd-info-bg);
            }

            &.ai-message {
                background: var(--nd-success-bg);
            }
        }

        .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;

            .sender {
                font-weight: 500;
                color: var(--nd-text-1);
                display: flex;
                align-items: center;
                gap: 4px;
            }

            .time {
                font-size: 12px;
                color: var(--nd-text-4);
            }
        }

        .message-content {
            color: var(--nd-text-1);
            line-height: 1.6;
            white-space: pre-wrap;
            margin-top: 8px;
            font-size: 14px;
        }
    }
}
</style>
