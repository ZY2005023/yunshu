<template>
    <div class="frontend-layout">
        <!-- 顶部导航：滚动后加毛玻璃，避免长页面滚动时导航「浮」在内容上 -->
        <header class="site-header" :class="{ 'is-scrolled': scrolled }">
            <div class="nd-container header-inner">
                <BrandLogo
                    class="brand"
                    title="云舒"
                    subtitle="AI 心理健康助手"
                    size="sm"
                    @click="router.push('/')"
                />

                <nav class="nav-section">
                    <router-link
                        v-for="item in navItems"
                        :key="item.path"
                        :to="item.path"
                        class="nav-link"
                    >
                        {{ item.label }}
                    </router-link>
                </nav>

                <div class="header-actions">
                    <template v-if="!isLoggedIn">
                        <router-link to="/auth/login" class="nav-link login-link">登录</router-link>
                        <el-button type="primary" round @click="router.push('/auth/register')">
                            免费注册
                        </el-button>
                    </template>

                    <el-dropdown v-else trigger="click">
                        <div class="user-entry">
                            <UserAvatar
                                :name="displayName"
                                :seed="userInfo.id || userInfo.username"
                                :size="34"
                            />
                            <span class="user-name">{{ displayName }}</span>
                            <el-icon class="chevron"><ArrowDown /></el-icon>
                        </div>
                        <template #dropdown>
                            <el-dropdown-menu>
                                <div class="user-card">
                                    <UserAvatar
                                        :name="displayName"
                                        :seed="userInfo.id || userInfo.username"
                                        :size="40"
                                    />
                                    <div class="user-card__text">
                                        <p class="user-card__name">{{ displayName }}</p>
                                        <p class="user-card__mail">{{ userInfo.email || '未填写邮箱' }}</p>
                                    </div>
                                </div>
                                <el-dropdown-item @click="router.push('/consultation')">
                                    <el-icon><ChatDotRound /></el-icon>我的咨询
                                </el-dropdown-item>
                                <el-dropdown-item @click="router.push('/emotion-diary')">
                                    <el-icon><Notebook /></el-icon>我的日记
                                </el-dropdown-item>
                                <el-dropdown-item @click="router.push('/scale')">
                                    <el-icon><DataLine /></el-icon>我的测评
                                </el-dropdown-item>
                                <el-dropdown-item divided @click="router.push('/profile')">
                                    <el-icon><Setting /></el-icon>个人中心
                                </el-dropdown-item>
                                <el-dropdown-item @click="handleLogout">
                                    <el-icon><SwitchButton /></el-icon>退出登录
                                </el-dropdown-item>
                            </el-dropdown-menu>
                        </template>
                    </el-dropdown>
                </div>

                <!-- 小屏汉堡 -->
                <button class="menu-toggle" type="button" aria-label="打开菜单" @click="drawer = true">
                    <el-icon><Menu /></el-icon>
                </button>
            </div>
        </header>

        <main class="main-content" :class="{ 'main-content--flush': isFullHeight }">
            <router-view v-slot="{ Component }">
                <transition name="page-fade" mode="out-in">
                    <component :is="Component" />
                </transition>
            </router-view>
        </main>

        <!-- 全屏页（对话、日记）不显示页脚，否则会顶出多余滚动条 -->
        <footer v-if="!isFullHeight" class="site-footer">
            <div class="nd-container footer-inner">
                <div class="footer-brand">
                    <BrandLogo tone="dark" title="云舒" subtitle="AI 心理健康助手" size="sm" />
                    <p class="footer-desc">
                        用 AI 陪你把情绪说出来、记下来、看明白。<br />
                        我们不替代专业治疗，但会在你需要时，把你送到对的人面前。
                    </p>
                </div>

                <div class="footer-col">
                    <h4>功能</h4>
                    <a @click="go('/consultation')">AI 心理咨询</a>
                    <a @click="go('/emotion-diary')">情绪日记</a>
                    <a @click="go('/scale')">心理测评</a>
                    <a @click="go('/knowledge')">心理健康知识库</a>
                </div>

                <div class="footer-col">
                    <h4>求助资源</h4>
                    <span>全国心理援助热线 <b>12356</b></span>
                    <span>学校心理健康教育中心</span>
                    <span>紧急情况请拨打 120 / 110</span>
                </div>
            </div>

            <div class="footer-bottom">
                <div class="nd-container footer-bottom__inner">
                    <span>© {{ year }} 云舒 · 仅用于心理健康自助与辅助，不构成医学诊断</span>
                    <span>数据仅用于心理健康支持，不对其他同学公开</span>
                </div>
            </div>
        </footer>

        <!-- 小屏导航抽屉 -->
        <el-drawer v-model="drawer" direction="rtl" size="272px" :with-header="false">
            <div class="drawer-inner">
                <BrandLogo title="云舒" subtitle="AI 心理健康助手" size="sm" />
                <nav class="drawer-nav">
                    <router-link
                        v-for="item in navItems"
                        :key="item.path"
                        :to="item.path"
                        class="drawer-link"
                        @click="drawer = false"
                    >
                        <el-icon><component :is="item.icon" /></el-icon>
                        <span>{{ item.label }}</span>
                    </router-link>
                    <!-- 首页只对未登录用户展示：登录后被守卫弹回 /consultation，
                         放着就是一条点了没反应的死链接 -->
                    <a v-if="!isLoggedIn" class="drawer-link" @click="go('/')">首页</a>
                </nav>
                <div class="drawer-foot">
                    <template v-if="!isLoggedIn">
                        <el-button type="primary" class="drawer-btn" @click="go('/auth/login')">
                            登录
                        </el-button>
                        <el-button class="drawer-btn" @click="go('/auth/register')">注册</el-button>
                    </template>
                    <template v-else>
                        <p class="drawer-user">{{ displayName }}</p>
                        <el-button class="drawer-btn" @click="go('/profile')">个人中心</el-button>
                        <el-button class="drawer-btn" @click="handleLogout">退出登录</el-button>
                    </template>
                </div>
            </div>
        </el-drawer>
    </div>
</template>

<script setup>
/**
 * 用户端布局。
 *
 * 改版要点：
 *  - 导航改为吸顶 + 滚动后毛玻璃，长页面滚动时始终可达；
 *  - 补小屏汉堡抽屉（原来完全没有移动端导航）；
 *  - 补全局页脚：功能入口 + 求助资源 + 免责声明（心理类产品必备）；
 *  - 头像不再用外链占位图，改用 UserAvatar（真实昵称首字 + 稳定配色）；
 *  - 订阅路由 meta.fullHeight：对话、日记这类需要占满视口的页面自动隐藏页脚。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { logout, getCurrentUser } from '@/api/admin'
import { useUserStore } from '@/stores/user'
import BrandLogo from './BrandLogo.vue'
import UserAvatar from './UserAvatar.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const NAV_ITEMS = [
    { path: '/consultation', label: 'AI 咨询', icon: 'ChatDotRound' },
    { path: '/emotion-diary', label: '情绪日记', icon: 'Notebook' },
    { path: '/scale', label: '心理测评', icon: 'DataLine' },
    { path: '/knowledge', label: '知识库', icon: 'Reading' }
]

const navItems = NAV_ITEMS

const isLoggedIn = ref(false)
/**
 * 用户信息走 store（响应式），不再是自己解析一份 localStorage ——
 * 否则在个人中心改完昵称，导航栏还显示旧的。
 * 保留 `userInfo` 这个名字是为了模板里少改，本质是 store 里的那个 ref。
 */
const userInfo = computed(() => userStore.userInfo)
const drawer = ref(false)
const scrolled = ref(false)
const year = new Date().getFullYear()

/** 需要占满视口的页面：隐藏页脚 */
const isFullHeight = computed(() => Boolean(route.meta && route.meta.fullHeight))

const displayName = computed(
    () => userInfo.value.nickname || userInfo.value.displayName || userInfo.value.username || '用户'
)

const clearLocalAuth = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    userStore.clear()
}

const handleLogout = () => {
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
}

const go = (path) => {
    drawer.value = false
    router.push(path)
}

const onScroll = () => {
    scrolled.value = window.scrollY > 8
}

onMounted(async () => {
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()

    const token = localStorage.getItem('token')
    isLoggedIn.value = token !== null

    // 先用本地缓存渲染，避免头像区闪烁
    userStore.loadFromStorage()

    if (!token) return

    // 再向后端确认一次：token 可能已过期/被吊销，昵称也可能改过。
    // 之前只看 localStorage，过期后要等第一次业务请求失败才发现。
    try {
        const fresh = await getCurrentUser()
        userStore.setUserInfo(fresh)
        isLoggedIn.value = true
    } catch (e) {
        // 401 已由 request 层统一处理（清登录态 + 跳登录），这里不重复
        isLoggedIn.value = false
    }
})

onUnmounted(() => {
    window.removeEventListener('scroll', onScroll)
})
</script>

<style scoped lang="scss">
.frontend-layout {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    background: var(--nd-bg);
}

/* ---------- 顶部导航 ---------- */
.site-header {
    position: sticky;
    top: 0;
    z-index: 100;
    height: var(--nd-navbar-h);
    background: rgba(255, 255, 255, 0.86);
    backdrop-filter: saturate(180%) blur(12px);
    border-bottom: 1px solid transparent;
    transition:
        border-color var(--nd-duration) var(--nd-ease),
        box-shadow var(--nd-duration) var(--nd-ease);

    &.is-scrolled {
        border-bottom-color: var(--nd-border);
        box-shadow: var(--nd-shadow-xs);
    }
}

.header-inner {
    height: var(--nd-navbar-h);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--nd-gap-lg);
}

.brand {
    cursor: pointer;
    flex: none;
}

.nav-section {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    justify-content: center;
}

.nav-link {
    position: relative;
    padding: 8px 14px;
    border-radius: var(--nd-radius-sm);
    font-size: 15px;
    font-weight: 500;
    color: var(--nd-text-2);
    transition:
        color var(--nd-duration) var(--nd-ease),
        background var(--nd-duration) var(--nd-ease);

    &:hover {
        color: var(--nd-primary-600);
        background: var(--nd-primary-50);
    }

    /* Vue Router 自动加的高亮类 */
    &.router-link-active {
        color: var(--nd-primary-600);
        font-weight: 600;

        &::after {
            content: '';
            position: absolute;
            left: 14px;
            right: 14px;
            bottom: 2px;
            height: 2px;
            border-radius: 2px;
            background: var(--nd-primary-500);
        }
    }
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: none;
}

.login-link {
    padding: 8px 10px;
}

.user-entry {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 10px 4px 4px;
    border-radius: var(--nd-radius-full);
    cursor: pointer;
    transition: background var(--nd-duration) var(--nd-ease);

    &:hover {
        background: var(--nd-primary-50);
    }

    .user-name {
        max-width: 92px;
        font-size: 14px;
        font-weight: 500;
        color: var(--nd-text-2);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .chevron {
        font-size: 12px;
        color: var(--nd-text-4);
    }
}

/* 下拉里的用户信息卡 */
.user-card {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px 12px;
    margin-bottom: 4px;
    border-bottom: 1px solid var(--nd-border);

    &__text {
        min-width: 0;
    }
    &__name {
        font-size: 14px;
        font-weight: 600;
        color: var(--nd-text-1);
        line-height: 1.4;
    }
    &__mail {
        font-size: 12px;
        color: var(--nd-text-4);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        max-width: 160px;
    }
}

.menu-toggle {
    display: none;
    width: 40px;
    height: 40px;
    border: 1px solid var(--nd-border);
    border-radius: var(--nd-radius-sm);
    background: var(--nd-surface);
    color: var(--nd-text-2);
    font-size: 18px;
    cursor: pointer;
}

/* ---------- 主内容 ---------- */
.main-content {
    flex: 1;
    width: 100%;
}

/* 全屏页：去掉底部留白 */
.main-content--flush {
    padding-bottom: 0;
}

/* 路由切换过渡 */
.page-fade-enter-active,
.page-fade-leave-active {
    transition: opacity 0.2s var(--nd-ease);
}
.page-fade-enter-from,
.page-fade-leave-to {
    opacity: 0;
}

/* ---------- 页脚 ---------- */
.site-footer {
    margin-top: auto;
    background: linear-gradient(180deg, #1c6b63 0%, #14514b 100%);
    color: rgba(255, 255, 255, 0.78);
}

.footer-inner {
    display: grid;
    grid-template-columns: 1.6fr 1fr 1.2fr;
    gap: var(--nd-gap-xl);
    padding-top: 48px;
    padding-bottom: 36px;
}

.footer-brand {
    .footer-desc {
        margin-top: 16px;
        font-size: 13px;
        line-height: 1.9;
        color: rgba(255, 255, 255, 0.62);
    }
}

.footer-col {
    display: flex;
    flex-direction: column;
    gap: 10px;

    h4 {
        margin-bottom: 6px;
        font-size: 14px;
        font-weight: 600;
        color: #fff;
    }

    a,
    span {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.66);
        cursor: pointer;
        transition: color var(--nd-duration) var(--nd-ease);
    }

    a:hover {
        color: #fff;
    }

    b {
        color: #ffd985;
    }
}

.footer-bottom {
    border-top: 1px solid rgba(255, 255, 255, 0.1);

    &__inner {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--nd-gap);
        flex-wrap: wrap;
        padding-top: 18px;
        padding-bottom: 22px;
        font-size: 12px;
        color: rgba(255, 255, 255, 0.5);
    }
}

/* ---------- 移动抽屉 ---------- */
.drawer-inner {
    display: flex;
    flex-direction: column;
    gap: 22px;
    height: 100%;
}

.drawer-nav {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
}

.drawer-link {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: var(--nd-radius-sm);
    font-size: 15px;
    color: var(--nd-text-2);
    cursor: pointer;

    &:hover,
    &.router-link-active {
        background: var(--nd-primary-50);
        color: var(--nd-primary-600);
    }
}

.drawer-foot {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-top: 18px;
    border-top: 1px solid var(--nd-border);

    .drawer-btn {
        width: 100%;
        margin: 0;
    }

    .drawer-user {
        font-size: 14px;
        font-weight: 600;
        color: var(--nd-text-1);
        text-align: center;
    }
}

/* ---------- 响应式 ---------- */
@media (max-width: 900px) {
    .nav-section,
    .header-actions {
        display: none;
    }
    .menu-toggle {
        display: grid;
        place-items: center;
    }
    .footer-inner {
        grid-template-columns: 1fr;
        gap: var(--nd-gap-lg);
        padding-top: 36px;
        padding-bottom: 24px;
    }
}
</style>
