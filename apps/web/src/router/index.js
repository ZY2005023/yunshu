import { createRouter, createWebHistory } from 'vue-router'
import BackendLayout from '@/components/BackendLayout.vue'
import AuthLayout from '@/components/AuthLayout.vue'
import FrontendLayout from '@/components/FrontendLayout.vue'


// 路由配置
const backendRoutes = [
    {
        path: '/back',
        redirect: '/back/dashboard',
        component: BackendLayout,
        // meta.group 供侧边栏分组展示使用；侧边栏只负责渲染，不再自己维护菜单清单
        children: [
            {
                path: 'dashboard',
                component: () => import('@/views/dashboard.vue'),
                meta: {
                    title: '数据分析',
                    icon: 'PieChart',
                    group: '概览'
                }
            },
            {
                path: 'crisis',
                component: () => import('@/views/crisis.vue'),
                meta: {
                    title: '危机预警',
                    icon: 'Warning',
                    group: '预警与评估'
                }
            },
            {
                path: 'scales',
                component: () => import('@/views/scaleRecords.vue'),
                meta: {
                    title: '量表记录',
                    icon: 'Notebook',
                    group: '预警与评估'
                }
            },
            {
                path: 'consultations',
                component: () => import('@/views/consultations.vue'),
                meta: {
                    title: '咨询记录',
                    icon: 'Message',
                    group: '用户数据'
                }
            },
            {
                path: 'emotional',
                component: () => import('@/views/emotional.vue'),
                meta: {
                    title: '情绪日志',
                    icon: 'User',
                    group: '用户数据'
                }
            },
            {
                path: 'knowledge',
                component: () => import('@/views/knowledge.vue'),
                meta: {
                    title: '知识文章',
                    icon: 'ChatLineSquare',
                    group: '内容管理'
                }
            },
            {
                path: 'users',
                component: () => import('@/views/users.vue'),
                meta: {
                    title: '用户管理',
                    icon: 'UserFilled',
                    group: '用户数据'
                }
            },
            {
                path: 'ai-config',
                component: () => import('@/views/aiConfig.vue'),
                meta: {
                    title: 'API 管理',
                    icon: 'Connection',
                    group: '系统'
                }
            }
        ]
    },
    {
        path: '/auth',
        component: AuthLayout,
        children: [
            {
                path: 'login',
                component: () => import('@/views/login.vue'),
                meta: {
                    title: '登录'
                }
            },
            {
                path: 'register',
                component: () => import('@/views/register.vue'),
                meta: {
                    title: '注册'
                }
            }
        ]
    }
]

const frontendRoutes = [
    {
        path: '/',
        component: FrontendLayout,
        children: [
            {
                path: '',
                component: () => import('@/views/home.vue'),
                meta: { title: '首页' }
            },
            {
                path: 'consultation',
                component: () => import('@/views/consultation.vue'),
                // fullHeight：布局层隐藏页脚，让对话区占满视口
                meta: { title: 'AI 心理咨询', fullHeight: true }
            },
            {
                path: 'emotion-diary',
                component: () => import('@/views/emotionDiary.vue'),
                meta: { title: '情绪日记', fullHeight: true }
            },
            {
                path: 'knowledge',
                component: () => import('@/views/frontendKnowledge.vue'),
                meta: { title: '心理健康知识库' }
            },
            {
                path: 'knowledge/article/:id',
                component: () => import('@/views/articleDetail.vue'),
                props: true,
                meta: { title: '文章详情' }
            },
            {
                path: 'scale',
                component: () => import('@/views/scale.vue'),
                meta: { title: '心理测评' }
            },
            {
                path: 'profile',
                component: () => import('@/views/profile.vue'),
                meta: { title: '个人中心' }
            }
        ]
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes: [ ...backendRoutes, ...frontendRoutes]
})

// 需要登录才能访问的用户端页面
const AUTH_REQUIRED_PATHS = [
    '/consultation',
    '/emotion-diary',
    '/knowledge',
    '/scale',
    '/profile'
]

// 路由前置守卫
router.beforeEach((to, from, next) => {
    const token = localStorage.getItem('token')
    const userInfoStr = localStorage.getItem('userInfo')
    // localStorage 可能被残留脚本/手工改坏 —— 解析失败当未登录处理，
    // 不能让守卫本身抛错把整个应用卡死
    let userInfo = null
    if (token && userInfoStr) {
        try {
            userInfo = JSON.parse(userInfoStr)
        } catch (e) {
            userInfo = null
        }
    }

    // ---------- 已登录 ----------
    if (token && userInfo) {
        // 管理员：主要在后台工作，访问任何前台/登录页都带回看板；
        // 例外：/profile —— 管理员也需要能改自己的资料和密码
        // （后端 PUT /api/user/profile 对管理员同样有效）。
        // 用 Number() 显式转换：userInfo 来自 localStorage 反序列化，
        // 历史上出现过 userType 被存成字符串 "2" 的情况
        if (Number(userInfo.userType) === 2) {
            if (to.path.startsWith('/back') || to.path === '/profile') {
                next()
            } else {
                next('/back/dashboard')
            }
            return
        }
        // 普通用户：登录后不再看登录/注册页和首页
        if (to.path.startsWith('/auth')) {
            next('/consultation')
            return
        }
        if (to.path === '/') {
            next('/consultation')
            return
        }
        // 普通用户不能进后台
        if (to.path.startsWith('/back')) {
            next('/consultation')
            return
        }
        next()
        return
    }

    // ---------- 未登录 ----------
    // 后台页面 → 登录页
    if (to.path.startsWith('/back')) {
        next('/auth/login')
        return
    }
    // 需要登录的功能页 → 登录页并携带回跳地址
    if (AUTH_REQUIRED_PATHS.some(p => to.path === p || to.path.startsWith(p + '/'))) {
        next({ path: '/auth/login', query: { redirect: to.fullPath } })
        return
    }
    next()
})

// 路由后置钩子：把 meta.title 同步到浏览器标签标题
router.afterEach((to) => {
    const t = to.meta && to.meta.title
    document.title = t ? `${t} · 云舒` : '云舒 · AI 心理健康助手'
})

export default router
