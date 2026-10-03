<template>
    <div class="navbar">
        <div class="nav-left">
            <button class="icon-btn" type="button" :title="isCollapse ? '展开菜单' : '收起菜单'" @click="toggleCollapse">
                <el-icon><component :is="isCollapse ? 'Expand' : 'Fold'" /></el-icon>
            </button>

            <el-breadcrumb class="crumb" separator="/">
                <el-breadcrumb-item>管理后台</el-breadcrumb-item>
                <el-breadcrumb-item v-if="group">{{ group }}</el-breadcrumb-item>
                <el-breadcrumb-item>
                    <span class="crumb-current">{{ pageTitle }}</span>
                </el-breadcrumb-item>
            </el-breadcrumb>
        </div>

        <div class="nav-right">
            <!-- 「前台首页」按钮已移除：路由守卫会把管理员从 / 弹回看板，
                 点了等于没点（死按钮）。管理员要改资料走 /profile（守卫已放行） -->

            <el-dropdown trigger="click" @command="handleCommand">
                <div class="user-entry">
                    <UserAvatar :name="displayName" :seed="userInfo.id || userInfo.username" :size="34" />
                    <div class="user-meta">
                        <span class="user-name">{{ displayName }}</span>
                        <span class="user-role">管理员</span>
                    </div>
                    <el-icon class="chevron"><ArrowDown /></el-icon>
                </div>
                <template #dropdown>
                    <el-dropdown-menu>
                        <el-dropdown-item disabled>
                            <span class="dd-account">{{ userInfo.email || userInfo.username || '—' }}</span>
                        </el-dropdown-item>
                        <el-dropdown-item divided command="logout">
                            <el-icon><SwitchButton /></el-icon>退出登录
                        </el-dropdown-item>
                    </el-dropdown-menu>
                </template>
            </el-dropdown>
        </div>
    </div>
</template>

<script setup>
/**
 * 管理端顶栏。
 *
 * 修掉的问题：
 *  - 用户名原来硬编码 "admin"、头像用外链占位图 —— 现在读真实登录信息；
 *  - 只有一个页面标题，层级感弱 —— 补面包屑（管理后台 / 分组 / 当前页）；
 *  - 登出没带 refreshToken，后端无法吊销 —— 补上（与用户端保持一致）。
 */
import { computed, ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAdminStore } from '@/stores/admin'
import { logout } from '@/api/admin'
import UserAvatar from './UserAvatar.vue'

const router = useRouter()
const route = useRoute()
const store = useAdminStore()

const isCollapse = computed(() => store.isCollapse)
const userInfo = ref({})

const pageTitle = computed(() => (route.meta && route.meta.title) || '管理后台')
const group = computed(() => (route.meta && route.meta.group) || '')

const displayName = computed(
    () => userInfo.value.nickname || userInfo.value.displayName || userInfo.value.username || '管理员'
)

const toggleCollapse = () => store.toggleCollapse()

const clearLocalAuth = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('userInfo')
}

const handleCommand = (command) => {
    if (command !== 'logout') return
    ElMessageBox.confirm('确定要退出登录吗？', '退出确认', {
        confirmButtonText: '退出',
        cancelButtonText: '再想想',
        type: 'warning'
    })
        .then(() => {
            // 把 refreshToken 一并交给后端吊销
            logout(localStorage.getItem('refreshToken'))
                .then(() => {
                    clearLocalAuth()
                    router.push('/auth/login')
                })
                .catch(() => {
                    // 后端不可用时也允许本地登出
                    clearLocalAuth()
                    router.push('/auth/login')
                })
        })
        .catch(() => {
            // 取消：什么也不做（ElMessageBox 取消会走 reject）
        })
}

onMounted(() => {
    const infoStr = localStorage.getItem('userInfo')
    if (!infoStr) return
    try {
        userInfo.value = JSON.parse(infoStr) || {}
    } catch (e) {
        userInfo.value = {}
        ElMessage.warning('本地登录信息已损坏，建议重新登录')
    }
})
</script>

<style lang="scss" scoped>
.navbar {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--nd-gap);
    padding: 0 20px;
    background: var(--nd-surface);
}

.nav-left,
.nav-right {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
}

.icon-btn {
    width: 36px;
    height: 36px;
    display: grid;
    place-items: center;
    border: 1px solid var(--nd-border);
    border-radius: var(--nd-radius-sm);
    background: var(--nd-surface);
    color: var(--nd-text-3);
    font-size: 16px;
    cursor: pointer;
    transition: all var(--nd-duration) var(--nd-ease);
    flex: none;

    &:hover {
        color: var(--nd-primary-600);
        border-color: var(--nd-primary-200);
        background: var(--nd-primary-50);
    }
}

.crumb {
    :deep(.el-breadcrumb__inner) {
        color: var(--nd-text-3);
        font-weight: 400;
    }
    :deep(.el-breadcrumb__separator) {
        color: var(--nd-text-4);
    }
    .crumb-current {
        color: var(--nd-text-1);
        font-weight: 600;
    }
}

.user-entry {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 10px 4px 4px;
    border-radius: var(--nd-radius-full);
    cursor: pointer;
    transition: background var(--nd-duration) var(--nd-ease);

    &:hover {
        background: var(--nd-primary-50);
    }

    .user-meta {
        display: flex;
        flex-direction: column;
        line-height: 1.25;
    }

    .user-name {
        font-size: 14px;
        font-weight: 600;
        color: var(--nd-text-1);
    }

    .user-role {
        font-size: 11.5px;
        color: var(--nd-text-4);
    }

    .chevron {
        font-size: 12px;
        color: var(--nd-text-4);
    }
}

.dd-account {
    font-size: 12px;
    color: var(--nd-text-4);
    cursor: default;
}

@media (max-width: 768px) {
    .crumb {
        display: none;
    }
    .user-meta {
        display: none;
    }
}
</style>
