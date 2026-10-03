<template>
    <div>
        <PageHead title="用户管理" subtitle="启用/禁用账号、重置密码 —— 也是「忘记密码」的最终出口" />

        <el-alert type="info" :closable="false" class="intro-alert">
            <p>
                <b>禁用</b>会让该用户当前所有登录立刻失效，且无法再登录；
                <b>重置密码</b>不需要原密码，用于用户忘记密码时协助恢复，重置后对方同样需要重新登录。
            </p>
            <p>
                为避免把自己锁在门外：<b>不能修改自己的账号状态</b>，系统也会拒绝禁用最后一个可用管理员。
            </p>
        </el-alert>

        <TableSearch :formItem="formItem" @search="handleSearch" />

        <el-table :data="tableData" style="width: 100%">
            <el-table-column label="用户" min-width="180">
                <template #default="scope">
                    <div class="user-cell">
                        <UserAvatar
                            :name="scope.row.nickname || scope.row.username"
                            :seed="scope.row.id"
                            :size="32"
                        />
                        <div>
                            <div class="user-cell__name">
                                {{ scope.row.nickname || scope.row.username || '-' }}
                                <span v-if="isMe(scope.row)" class="me-tag">我</span>
                            </div>
                            <div class="user-cell__sub">@{{ scope.row.username }}</div>
                        </div>
                    </div>
                </template>
            </el-table-column>

            <el-table-column prop="email" label="邮箱" min-width="150" show-overflow-tooltip />

            <el-table-column label="类型" width="92">
                <template #default="scope">
                    <el-tag :type="scope.row.userType === 2 ? 'warning' : 'info'" size="small">
                        {{ scope.row.userTypeDisplayName }}
                    </el-tag>
                </template>
            </el-table-column>

            <el-table-column label="状态" width="84">
                <template #default="scope">
                    <el-tag :type="scope.row.status === 1 ? 'success' : 'danger'" size="small">
                        {{ scope.row.statusDisplayName }}
                    </el-tag>
                </template>
            </el-table-column>

            <el-table-column label="注册时间" width="110">
                <template #default="scope">
                    {{ String(scope.row.createdAt || '').slice(0, 10) || '—' }}
                </template>
            </el-table-column>

            <el-table-column label="操作" width="190" fixed="right">
                <template #default="scope">
                    <div class="row-actions">
                        <el-button
                            text
                            :type="scope.row.status === 1 ? 'danger' : 'success'"
                            :disabled="isMe(scope.row)"
                            @click="toggleStatus(scope.row)"
                        >
                            {{ scope.row.status === 1 ? '禁用' : '启用' }}
                        </el-button>
                        <el-button text type="primary" @click="openReset(scope.row)">
                            重置密码
                        </el-button>
                    </div>
                </template>
            </el-table-column>
        </el-table>

        <el-pagination
            style="margin-top: 25px"
            :page-size="pagination.size"
            layout="prev, pager, next"
            :total="pagination.total"
            @change="handleChange"
        />

        <el-dialog v-model="pwdVisible" title="重置密码" width="440px">
            <p class="dialog-tip">
                将为用户
                <b>{{ target && (target.nickname || target.username) }}</b>
                设置新密码。该用户的所有登录会立即失效，需要重新登录。
            </p>
            <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-position="top">
                <el-form-item label="新密码" prop="newPassword">
                    <el-input
                        v-model="pwdForm.newPassword"
                        type="password"
                        show-password
                        placeholder="6-64 位"
                    />
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="pwdVisible = false">取消</el-button>
                <el-button type="primary" :loading="resetting" @click="submitReset">
                    确认重置
                </el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
/**
 * 管理端 · 用户管理。
 *
 * 原版完全没有这一组能力，导致两个问题：
 *  1. `deps.py` 里 `user.status != 1 → 403` 的校验**永远不会触发** ——
 *     没有任何途径把 status 改成非 1，那段安全逻辑等于死代码。
 *  2. 用户端「忘记密码」提示去找管理员重置，而管理员**没有重置能力** —— 断链。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageHead from '@/components/PageHead.vue'
import TableSearch from '@/components/TableSearch.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { getUserPage, resetUserPassword, setUserStatus } from '@/api/admin'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

const formItem = [
    { prop: 'keyword', label: '关键词', comp: 'input', placeholder: '用户名 / 昵称 / 邮箱' },
    {
        prop: 'userType',
        label: '类型',
        comp: 'select',
        placeholder: '全部',
        options: [
            { label: '普通用户', value: 1 },
            { label: '管理员', value: 2 }
        ]
    },
    {
        prop: 'status',
        label: '状态',
        comp: 'select',
        placeholder: '全部',
        options: [
            { label: '正常', value: 1 },
            { label: '禁用', value: 0 }
        ]
    }
]

const tableData = ref([])
const pagination = ref({ currentPage: 1, size: 10, total: 0 })
const filters = ref({})

const pwdVisible = ref(false)
const resetting = ref(false)
const target = ref(null)
const pwdFormRef = ref(null)
const pwdForm = reactive({ newPassword: '' })

const pwdRules = {
    newPassword: [
        { required: true, message: '请输入新密码', trigger: 'blur' },
        { min: 6, max: 64, message: '密码需 6-64 位', trigger: 'blur' }
    ]
}

const myId = computed(() => userStore.userInfo.id)
/** 后端也会拦，这里禁用按钮是为了让管理员一眼明白为什么不能点 */
const isMe = (row) => myId.value != null && row.id === myId.value

const loadData = async () => {
    const params = {
        currentPage: pagination.value.currentPage,
        size: pagination.value.size,
        ...filters.value
    }
    Object.keys(params).forEach((k) => {
        if (params[k] === '' || params[k] === null || params[k] === undefined) delete params[k]
    })

    const res = await getUserPage(params)
    tableData.value = res.records || []
    pagination.value.total = res.total || 0
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

const toggleStatus = async (row) => {
    const disabling = row.status === 1
    const name = row.nickname || row.username
    try {
        await ElMessageBox.confirm(
            disabling
                ? `禁用后「${name}」将立刻退出登录，且无法再登录。确认禁用？`
                : `确认恢复「${name}」的登录权限？`,
            disabling ? '禁用账号' : '启用账号',
            { type: 'warning', confirmButtonText: disabling ? '确认禁用' : '确认启用' }
        )
    } catch {
        return // 用户取消
    }

    await setUserStatus(row.id, disabling ? 0 : 1)
    ElMessage.success(disabling ? '已禁用' : '已启用')
    loadData()
}

const openReset = (row) => {
    target.value = row
    pwdForm.newPassword = ''
    pwdVisible.value = true
}

const submitReset = () => {
    pwdFormRef.value?.validate(async (valid) => {
        if (!valid || resetting.value) return
        resetting.value = true
        try {
            await resetUserPassword(target.value.id, pwdForm.newPassword)
            ElMessage.success('密码已重置，请告知用户使用新密码登录')
            pwdVisible.value = false
            loadData()
        } catch (e) {
            // 请求层已统一提示
        } finally {
            resetting.value = false
        }
    })
}

onMounted(loadData)
</script>

<style scoped>
.intro-alert {
    margin-bottom: 16px;
}

.intro-alert p {
    margin: 0 0 6px;
    line-height: 1.7;
}

.intro-alert p:last-child {
    margin-bottom: 0;
}

.user-cell {
    display: flex;
    align-items: center;
    gap: 10px;
}

.user-cell__name {
    font-weight: 500;
    color: var(--nd-text-1);
}

.user-cell__sub {
    font-size: 12px;
    color: var(--nd-text-4);
}

.me-tag {
    display: inline-block;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: var(--nd-radius-full);
    background: var(--nd-primary-50);
    color: var(--nd-primary-700);
    font-size: 11.5px;
}

.dialog-tip {
    margin: 0 0 14px;
    font-size: 13.5px;
    line-height: 1.7;
    color: var(--nd-text-2);
}

.dialog-tip b {
    color: var(--nd-text-1);
}

/* 两个操作按钮必须同一行：默认 inline-block 会被挤成两行 */
.row-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;

    :deep(.el-button + .el-button) {
        margin-left: 0;
    }
}
</style>
