<template>
    <el-aside :width="isCollapse ? '76px' : '252px'" class="sidebar">
        <div class="side-brand">
            <BrandLogo
                :icon-only="isCollapse"
                :title="isCollapse ? '' : '云舒'"
                :subtitle="isCollapse ? '' : '管理后台'"
                size="sm"
            />
        </div>

        <el-menu
            :collapse="isCollapse"
            :collapse-transition="false"
            :default-active="route.path"
            router
            class="side-menu"
        >
            <template v-for="g in groups" :key="g.title">
                <p v-show="!isCollapse" class="group-title">{{ g.title }}</p>

                <el-menu-item
                    v-for="item in g.items"
                    :key="item.path"
                    :index="`/back/${item.path}`"
                    :class="{ 'has-crisis': item.path === 'crisis' && pendingCrisis > 0 }"
                >
                    <el-icon><component :is="item.meta.icon" /></el-icon>
                    <template #title>
                        <span class="menu-label">{{ item.meta.title }}</span>
                        <!-- 待处理危机数量：让管理员一眼看到有没有新工单 -->
                        <span v-if="item.path === 'crisis' && pendingCrisis > 0" class="crisis-badge">
                            {{ pendingCrisis > 99 ? '99+' : pendingCrisis }}
                        </span>
                    </template>
                </el-menu-item>
            </template>
        </el-menu>

        <div v-show="!isCollapse" class="side-foot">
            <p>心理健康 AI 助手</p>
            <p class="side-foot__ver">管理后台 v1.0</p>
        </div>
    </el-aside>
</template>

<script setup>
/**
 * 管理端侧边栏。
 *
 * 修掉的问题：
 *  1. 原来写死 `default-active="2"` —— 菜单高亮永远停在第二项，看不出当前在哪。
 *     改为绑定 route.path，跟随路由自动高亮（配合 el-menu 的 router 模式，
 *     点击即跳转，不再手工拼接路径）。
 *  2. 菜单清单原来依赖 `router.options.routes[0]`，一旦顶层路由顺序变动就会取错。
 *     改为按 path 显式查找 `/back`，并支持按 meta.group 分组渲染。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import { getCrisisPendingCount } from '@/api/admin'
import BrandLogo from './BrandLogo.vue'

const route = useRoute()
const router = useRouter()
const store = useAdminStore()

const isCollapse = computed(() => store.isCollapse)

/** 待处理的危机工单数，侧边栏角标用 */
const pendingCrisis = ref(0)

/** 从路由表推导分组菜单，保证「菜单即路由」这一单一数据源 */
const groups = computed(() => {
    const back = router.options.routes.find((r) => r.path === '/back')
    const children = (back && back.children) || []
    const order = []
    const map = new Map()

    children.forEach((c) => {
        const g = (c.meta && c.meta.group) || '其他'
        if (!map.has(g)) {
            map.set(g, [])
            order.push(g)
        }
        map.get(g).push(c)
    })

    return order.map((title) => ({ title, items: map.get(title) }))
})

onMounted(async () => {
    try {
        pendingCrisis.value = await getCrisisPendingCount()
    } catch (e) {
        // 拉不到就不显示角标，不阻塞侧边栏渲染
        pendingCrisis.value = 0
    }
})
</script>

<style lang="scss" scoped>
.sidebar {
    display: flex;
    flex-direction: column;
    background: var(--nd-surface);
    border-right: 1px solid var(--nd-border);
    transition: width var(--nd-duration) var(--nd-ease);
    overflow: hidden;
}

.side-brand {
    display: flex;
    align-items: center;
    height: var(--nd-navbar-h);
    padding: 0 18px;
    border-bottom: 1px solid var(--nd-border);
    flex: none;
}

.side-menu {
    flex: 1;
    border-right: 0;
    padding: 12px 0;
    overflow-y: auto;
    overflow-x: hidden;

    :deep(.el-menu-item) {
        height: 44px;
        line-height: 44px;
        margin: 3px 12px;
        padding-left: 14px !important;
        border-radius: var(--nd-radius-sm);
        color: var(--nd-text-2);
        font-size: 14.5px;
        transition:
            background var(--nd-duration) var(--nd-ease),
            color var(--nd-duration) var(--nd-ease);

        &:hover {
            background: var(--nd-surface-soft);
            color: var(--nd-text-1);
        }

        &.is-active {
            background: var(--nd-primary-50);
            color: var(--nd-primary-700);
            font-weight: 600;

            .el-icon {
                color: var(--nd-primary-600);
            }
        }

        .el-icon {
            margin-right: 10px;
            font-size: 17px;
        }
    }

    /* 折叠态：去掉左右外边距，避免图标被挤偏 */
    &.el-menu--collapse {
        :deep(.el-menu-item) {
            margin: 3px 8px;
            padding-left: 0 !important;
            justify-content: center;

            .el-icon {
                margin-right: 0;
            }

            /* 折叠时用小红点代替数字角标 */
            &.has-crisis::after {
                content: '';
                position: absolute;
                top: 9px;
                right: 10px;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--nd-danger);
                box-shadow: 0 0 0 2px var(--nd-surface);
            }
        }
    }
}

.group-title {
    margin: 16px 26px 6px;
    font-size: 11.5px;
    font-weight: 600;
    letter-spacing: 0.1em;
    color: var(--nd-text-4);

    &:first-child {
        margin-top: 4px;
    }
}

.menu-label {
    flex: 1;
}

.crisis-badge {
    flex: none;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: var(--nd-radius-full);
    background: var(--nd-danger);
    color: #fff;
    font-size: 11.5px;
    font-weight: 600;
    line-height: 20px;
    text-align: center;
}

.side-foot {
    flex: none;
    padding: 14px 20px 18px;
    border-top: 1px solid var(--nd-border);
    font-size: 12px;
    color: var(--nd-text-4);

    &__ver {
        margin-top: 2px;
        color: var(--nd-text-4);
        opacity: 0.8;
    }
}
</style>
