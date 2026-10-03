<template>
    <div class="auth-layout">
        <!-- 左：品牌与价值说明。小屏会隐藏，只保留表单侧 -->
        <section class="auth-aside">
            <span class="glow glow--a"></span>
            <span class="glow glow--b"></span>
            <span class="glow glow--c"></span>

            <div class="aside-inner">
                <BrandLogo tone="dark" title="云舒" subtitle="AI 心理健康助手" />

                <h1 class="aside-title">
                    不必独自承受，<br />
                    我们一直在这里
                </h1>
                <p class="aside-desc">
                    每个深夜、每个难熬的时刻，都可以有人听你说。云舒提供 24 小时 AI 陪伴、
                    情绪记录与专业资源对接。
                </p>

                <ul class="aside-points">
                    <li v-for="(p, i) in points" :key="p.title" :style="{ '--nd-delay': `${0.1 + i * 0.08}s` }">
                        <span class="point-icon">
                            <el-icon><component :is="p.icon" /></el-icon>
                        </span>
                        <div class="point-body">
                            <p class="point-title">{{ p.title }}</p>
                            <p class="point-desc">{{ p.desc }}</p>
                        </div>
                    </li>
                </ul>

                <div class="aside-foot">
                    <p>
                        紧急情况请拨打全国心理援助热线
                        <b>12356</b>
                    </p>
                </div>
            </div>
        </section>

        <!-- 右：表单区，由子路由渲染 login / register -->
        <section class="auth-main">
            <router-view v-slot="{ Component }">
                <transition name="auth-fade" mode="out-in">
                    <component :is="Component" />
                </transition>
            </router-view>
        </section>
    </div>
</template>

<script setup>
/**
 * 认证页外壳。
 *
 * 改版要点：原来左侧只有一张机器人图和一句标语，信息密度太低，
 * 也没有任何「为什么可以信任这里」的交代。心理类产品的登录页恰恰是
 * 用户最犹豫的一步，所以补上三条价值点 + 求助热线兜底。
 */
import BrandLogo from './BrandLogo.vue'

const points = [
    {
        icon: 'ChatDotRound',
        title: '24 小时在线陪伴',
        desc: '任何时候想说话，都会有人回应'
    },
    {
        icon: 'FirstAidKit',
        title: '四级风险识别',
        desc: '识别到风险会主动给出求助资源'
    },
    {
        icon: 'Lock',
        title: '记录不对外公开',
        desc: '仅你与校心理老师可见'
    }
]
</script>

<style scoped lang="scss">
.auth-layout {
    display: flex;
    min-height: 100vh;
}

/* ---------- 左侧品牌区 ---------- */
.auth-aside {
    position: relative;
    flex: 1 1 52%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding: 48px;
    background:
        radial-gradient(120% 100% at 0% 0%, #2f9c8b 0%, #1c6b63 55%, #134a46 100%);

    /* 装饰光斑：让大面积渐变不死板 */
    .glow {
        position: absolute;
        border-radius: 50%;
        filter: blur(4px);
        pointer-events: none;
    }
    .glow--a {
        width: 380px;
        height: 380px;
        top: -120px;
        right: -80px;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.16) 0%, transparent 68%);
    }
    .glow--b {
        width: 320px;
        height: 320px;
        bottom: -100px;
        left: -60px;
        background: radial-gradient(circle, rgba(239, 171, 60, 0.22) 0%, transparent 70%);
    }
    .glow--c {
        width: 200px;
        height: 200px;
        top: 46%;
        left: 52%;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.08) 0%, transparent 70%);
    }

    .aside-inner {
        position: relative;
        z-index: 1;
        width: 100%;
        max-width: 440px;
        color: #fff;
    }

    .aside-title {
        margin: 42px 0 16px;
        font-size: 40px;
        line-height: 1.25;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #fff;
    }

    .aside-desc {
        font-size: 15px;
        line-height: 1.85;
        color: rgba(255, 255, 255, 0.78);
    }

    .aside-points {
        margin-top: 38px;
        display: flex;
        flex-direction: column;
        gap: 18px;

        li {
            display: flex;
            align-items: flex-start;
            gap: 14px;
            animation: nd-fade-up 0.55s var(--nd-ease) both;
            animation-delay: var(--nd-delay, 0s);
        }
    }

    .point-icon {
        flex: none;
        width: 38px;
        height: 38px;
        display: grid;
        place-items: center;
        border-radius: 12px;
        font-size: 18px;
        color: #fff;
        background: rgba(255, 255, 255, 0.14);
        border: 1px solid rgba(255, 255, 255, 0.18);
    }

    .point-title {
        font-size: 15px;
        font-weight: 600;
        color: #fff;
        line-height: 1.5;
    }

    .point-desc {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.66);
        line-height: 1.6;
    }

    .aside-foot {
        margin-top: 46px;
        padding-top: 22px;
        border-top: 1px solid rgba(255, 255, 255, 0.14);
        font-size: 13px;
        color: rgba(255, 255, 255, 0.7);

        b {
            color: #ffd985;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
    }
}

/* ---------- 右侧表单区 ---------- */
.auth-main {
    flex: 1 1 48%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 48px 24px;
    background: var(--nd-surface);
}

/* 路由切换动画，避免登录↔注册时生硬跳变 */
.auth-fade-enter-active,
.auth-fade-leave-active {
    transition:
        opacity 0.2s var(--nd-ease),
        transform 0.2s var(--nd-ease);
}
.auth-fade-enter-from {
    opacity: 0;
    transform: translateX(12px);
}
.auth-fade-leave-to {
    opacity: 0;
    transform: translateX(-12px);
}

/* ---------- 响应式 ---------- */
@media (max-width: 1024px) {
    .auth-aside {
        padding: 36px;
        .aside-title {
            font-size: 32px;
        }
    }
}

@media (max-width: 860px) {
    .auth-layout {
        display: block;
    }
    .auth-aside {
        /* 小屏不再占满一屏，只作为顶部品牌条 */
        padding: 28px 24px;
        align-items: flex-start;

        .aside-inner {
            max-width: none;
        }
        .aside-title {
            margin: 22px 0 10px;
            font-size: 26px;
        }
        .aside-desc,
        .aside-points li:nth-child(n + 2),
        .aside-foot {
            display: none;
        }
        .aside-points {
            margin-top: 18px;
        }
    }
    .auth-main {
        padding: 32px 20px 56px;
        align-items: flex-start;
    }
}
</style>
