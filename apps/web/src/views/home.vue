<template>
    <div class="home">
        <!-- ============ Hero ============ -->
        <section class="hero">
            <span class="glow glow--a"></span>
            <span class="glow glow--b"></span>
            <span class="glow glow--c"></span>

            <div class="nd-container hero-inner">
                <div class="hero-text">
                    <span class="nd-badge nd-badge--accent">24 小时在线的 AI 心理陪伴</span>

                    <h1 class="hero-title">
                        一次温暖的对话<br />
                        <span class="highlight">让心事有处安放</span>
                    </h1>

                    <p class="hero-desc">
                        不必独自承受。说出你的感受，云舒会认真听、陪你理清楚，
                        需要时把你送到对的人面前。
                    </p>

                    <div class="hero-actions">
                        <el-button type="primary" size="large" round @click="goWithAuth('/consultation')">
                            <el-icon><ChatDotRound /></el-icon>
                            开始倾诉
                        </el-button>
                        <el-button size="large" round class="ghost-btn" @click="goWithAuth('/scale')">
                            先做个心理测评
                        </el-button>
                    </div>

                    <ul class="hero-trust">
                        <li v-for="t in trust" :key="t">
                            <el-icon><Select /></el-icon>
                            <span>{{ t }}</span>
                        </li>
                    </ul>
                </div>

                <!-- 右侧：机器人 + 悬浮示意卡，表达「可对话、可记录、可评估」 -->
                <div class="hero-art">
                    <div class="art-circle">
                        <img :src="iconUrl" alt="AI 心理助手" />
                    </div>

                    <div class="art-card art-card--chat">
                        <span class="dot"></span>
                        <div class="bubble">最近总是睡不好，脑子停不下来…</div>
                    </div>

                    <div class="art-card art-card--mood">
                        <p class="card-label">本周情绪</p>
                        <div class="mood-bars">
                            <span
                                v-for="(h, i) in [40, 62, 48, 78, 88, 70, 92]"
                                :key="i"
                                :style="{ height: `${h}%` }"
                            ></span>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- ============ 功能 ============ -->
        <section class="section">
            <div class="nd-container">
                <div class="nd-section-head">
                    <h2 class="nd-section-title">四件事，帮你把状态看清楚</h2>
                    <p class="nd-section-sub">
                        从「说出来」到「看明白」，再到「找人帮忙」，每一步都有工具接着
                    </p>
                </div>

                <div class="feature-grid nd-stagger">
                    <article
                        v-for="(f, i) in features"
                        :key="f.title"
                        class="nd-card nd-card--hover feature-card"
                        :style="{ '--nd-delay': `${i * 0.07}s` }"
                        @click="goWithAuth(f.path)"
                    >
                        <span class="feature-icon" :style="{ background: f.bg, color: f.color }">
                            <el-icon><component :is="f.icon" /></el-icon>
                        </span>
                        <h3>{{ f.title }}</h3>
                        <p>{{ f.desc }}</p>
                        <ul class="feature-list">
                            <li v-for="p in f.points" :key="p">{{ p }}</li>
                        </ul>
                        <span class="feature-go">
                            进入<el-icon><Right /></el-icon>
                        </span>
                    </article>
                </div>
            </div>
        </section>

        <!-- ============ 流程 ============ -->
        <section class="section section--soft">
            <div class="nd-container">
                <div class="nd-section-head">
                    <h2 class="nd-section-title">它会怎么陪你</h2>
                    <p class="nd-section-sub">不是简单的聊天机器人，而是一条能被接住的路径</p>
                </div>

                <ol class="steps">
                    <li v-for="(s, i) in steps" :key="s.title" class="step">
                        <span class="step-no">{{ String(i + 1).padStart(2, '0') }}</span>
                        <div class="step-body">
                            <h3>{{ s.title }}</h3>
                            <p>{{ s.desc }}</p>
                        </div>
                    </li>
                </ol>
            </div>
        </section>

        <!-- ============ 能力数字（只陈述真实具备的能力，不编造用户量）============ -->
        <section class="section">
            <div class="nd-container stats">
                <div v-for="s in stats" :key="s.label" class="stat">
                    <p class="stat-value">{{ s.value }}</p>
                    <p class="stat-label">{{ s.label }}</p>
                </div>
            </div>
        </section>

        <!-- ============ CTA ============ -->
        <section class="cta-wrap">
            <div class="nd-container">
                <div class="cta">
                    <span class="cta-glow"></span>
                    <div class="cta-text">
                        <h2>现在就可以说点什么</h2>
                        <p>哪怕只是「今天有点累」，也算一个好的开始。</p>
                    </div>
                    <div class="cta-actions">
                        <el-button type="primary" size="large" round @click="goWithAuth('/consultation')">
                            开始倾诉
                        </el-button>
                        <el-button size="large" round class="ghost-btn cta-ghost" @click="goWithAuth('/knowledge')">
                            看看知识库
                        </el-button>
                    </div>
                </div>
            </div>
        </section>
    </div>
</template>

<script setup>
/**
 * 用户端首页。
 *
 * 改版要点：原来是「一屏 hero + 下方大空白」，用户看完不知道系统能做什么、
 * 该从哪进去。现改为完整落地页：Hero → 功能 → 流程 → 能力 → CTA，
 * 每个功能卡都可直接点进对应页面（未登录会经路由守卫引导去登录）。
 */
import { useRouter } from 'vue-router'

const router = useRouter()
const iconUrl = new URL('@/assets/images/robot-fill.png', import.meta.url).href

const trust = [
    '记录不对外公开，仅你与校心理老师可见',
    '风险识别会主动给出求助资源',
    '不替代专业治疗，但会帮你找到专业的人'
]

const features = [
    {
        icon: 'ChatDotRound',
        title: 'AI 心理咨询',
        path: '/consultation',
        bg: 'rgba(47,156,139,0.1)',
        color: '#23857a',
        desc: '随时开口，随时有人回应。话题怎么绕都可以。',
        points: ['支持多轮记忆，不用重复说背景', '危机词识别，会先给你求助资源', '回答会附上依据的知识库文章']
    },
    {
        icon: 'Notebook',
        title: '情绪日记',
        path: '/emotion-diary',
        bg: 'rgba(239,171,60,0.14)',
        color: '#d98f22',
        desc: '每天花一分钟，把今天的状态留下来。',
        points: ['记录心情分数与主导情绪', 'AI 生成情绪分析', '看得到一段时间的变化趋势']
    },
    {
        icon: 'DataLine',
        title: '心理测评',
        path: '/scale',
        bg: 'rgba(87,134,224,0.12)',
        color: '#3f68bd',
        desc: '用标准化量表，比「感觉不太好」更具体。',
        points: ['包含 PHQ-9 / GAD-7 标准量表', '结果自动分级并给出建议', '自伤相关题目命中会优先推求助资源']
    },
    {
        icon: 'Reading',
        title: '知识库',
        path: '/knowledge',
        bg: 'rgba(44,158,106,0.12)',
        color: '#1f7d52',
        desc: '关于情绪、压力、人际的那些事，都有解释。',
        points: ['按分类浏览心理健康文章', '内容会作为 AI 回答的依据', '科普向，不做诊断结论']
    }
]

const steps = [
    { title: '说出来', desc: '在对话里描述此刻的感受。AI 会先判断风险等级，再决定该怎么回你。' },
    { title: '被理解', desc: '结合知识库里的专业资料回答，给出具体能做的动作，而不是空泛安慰。' },
    { title: '记下来', desc: '把状态写进情绪日记，或做一次标准量表，让变化有据可查。' },
    { title: '需要时转介', desc: '如果风险偏高，会主动推送学校心理健康教育中心与心理援助热线 12356。' }
]

const stats = [
    { value: '24 小时', label: '随时可用的陪伴' },
    // ⚠️ 是 3 级，不是 4 级 —— 见 core/crisis.py 的 LEVEL_ATTENTION/WARNING/CRITICAL。
    //    与危机页的筛选项（关注/预警/危机）保持一致，别写成宣传用的虚数。
    { value: '3 级', label: '风险识别分级' },
    { value: '2 套', label: '标准心理量表' },
    { value: '全流程', label: '对话 · 记录 · 评估 · 转介' }
]

// 已登录直接进功能页；未登录由路由守卫引导到登录页并在登录后回跳
const goWithAuth = (path) => {
    if (localStorage.getItem('token')) {
        router.push(path)
    } else {
        router.push({ path: '/auth/login', query: { redirect: path } })
    }
}
</script>

<style scoped lang="scss">
.home {
    width: 100%;
}

/* ================= Hero ================= */
.hero {
    position: relative;
    overflow: hidden;
    padding: 72px 0 92px;
    background: linear-gradient(155deg, #e9f6f3 0%, #f4f8f7 46%, #eef6f4 100%);

    .glow {
        position: absolute;
        border-radius: 50%;
        pointer-events: none;
    }
    .glow--a {
        width: 520px;
        height: 520px;
        top: -180px;
        right: -120px;
        background: radial-gradient(circle, rgba(47, 156, 139, 0.16) 0%, transparent 68%);
    }
    .glow--b {
        width: 380px;
        height: 380px;
        bottom: -160px;
        left: -80px;
        background: radial-gradient(circle, rgba(239, 171, 60, 0.14) 0%, transparent 70%);
    }
    .glow--c {
        width: 240px;
        height: 240px;
        top: 42%;
        left: 46%;
        background: radial-gradient(circle, rgba(87, 134, 224, 0.1) 0%, transparent 70%);
    }
}

.hero-inner {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: 1.05fr 0.95fr;
    align-items: center;
    gap: var(--nd-gap-2xl);
}

.hero-title {
    margin: 20px 0 18px;
    font-size: 52px;
    line-height: 1.18;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--nd-text-1);

    .highlight {
        background: linear-gradient(100deg, var(--nd-primary-500), var(--nd-primary-300));
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
    }
}

.hero-desc {
    max-width: 460px;
    font-size: 16px;
    line-height: 1.9;
    color: var(--nd-text-3);
}

.hero-actions {
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    margin: 32px 0 30px;

    :deep(.el-button) {
        height: 48px;
        padding: 0 26px;
        font-size: 15px;
    }
}

.hero-trust {
    display: flex;
    flex-direction: column;
    gap: 10px;

    li {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13.5px;
        color: var(--nd-text-3);

        :deep(.el-icon) {
            color: var(--nd-primary-500);
            font-size: 15px;
        }
    }
}

/* 右侧插画区 */
.hero-art {
    position: relative;
    height: 380px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.art-circle {
    width: 258px;
    height: 258px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: linear-gradient(150deg, #fff, #e6f4f1);
    box-shadow:
        0 26px 60px rgba(28, 107, 99, 0.16),
        inset 0 1px 0 #fff;
    border: 1px solid rgba(255, 255, 255, 0.9);

    img {
        width: 132px;
        height: 132px;
        object-fit: contain;
    }
}

.art-card {
    position: absolute;
    background: #fff;
    border: 1px solid var(--nd-border);
    border-radius: var(--nd-radius);
    box-shadow: var(--nd-shadow);
    animation: float 5s ease-in-out infinite;
}

.art-card--chat {
    top: 16px;
    left: -6px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    max-width: 250px;
    animation-delay: 0.4s;

    .dot {
        flex: none;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--nd-primary-400);
    }
    .bubble {
        font-size: 13px;
        color: var(--nd-text-2);
    }
}

.art-card--mood {
    right: -4px;
    bottom: 22px;
    width: 172px;
    padding: 14px 16px;
    animation-delay: 1.1s;

    .card-label {
        font-size: 12px;
        color: var(--nd-text-3);
        margin-bottom: 10px;
    }
    .mood-bars {
        display: flex;
        align-items: flex-end;
        gap: 6px;
        height: 48px;

        span {
            flex: 1;
            border-radius: 3px 3px 0 0;
            background: linear-gradient(180deg, var(--nd-primary-300), var(--nd-primary-500));
        }
    }
}

@keyframes float {
    0%,
    100% {
        transform: translateY(0);
    }
    50% {
        transform: translateY(-9px);
    }
}

/* ================= 通用区块 ================= */
.section {
    padding: 76px 0;
}
.section--soft {
    background: var(--nd-surface);
}

/* ================= 功能卡 ================= */
.feature-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--nd-gap-lg);
}

.feature-card {
    padding: 26px 22px 22px;
    cursor: pointer;

    h3 {
        margin: 16px 0 8px;
        font-size: 17px;
    }

    > p {
        font-size: 13.5px;
        line-height: 1.75;
        color: var(--nd-text-3);
        min-height: 48px;
    }
}

.feature-icon {
    width: 46px;
    height: 46px;
    display: grid;
    place-items: center;
    border-radius: 14px;
    font-size: 22px;
}

.feature-list {
    margin-top: 14px;
    padding-top: 14px;
    border-top: 1px dashed var(--nd-border);
    display: flex;
    flex-direction: column;
    gap: 8px;

    li {
        position: relative;
        padding-left: 14px;
        font-size: 12.5px;
        line-height: 1.6;
        color: var(--nd-text-3);

        &::before {
            content: '';
            position: absolute;
            left: 0;
            top: 8px;
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: var(--nd-primary-300);
        }
    }
}

.feature-go {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    margin-top: 18px;
    font-size: 13px;
    font-weight: 500;
    color: var(--nd-primary-600);
    opacity: 0;
    transform: translateX(-4px);
    transition: all var(--nd-duration) var(--nd-ease);
}

.feature-card:hover .feature-go {
    opacity: 1;
    transform: none;
}

/* ================= 流程 ================= */
.steps {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--nd-gap-lg);
}

.step {
    position: relative;
    padding-top: 22px;
    border-top: 2px solid var(--nd-border);

    /* 每步顶部一小段品牌色，作为进度感 */
    &::before {
        content: '';
        position: absolute;
        top: -2px;
        left: 0;
        width: 44px;
        height: 2px;
        background: var(--nd-primary-500);
    }

    .step-no {
        display: block;
        font-size: 26px;
        font-weight: 700;
        font-family: var(--nd-font-mono);
        color: var(--nd-primary-200);
        line-height: 1;
        margin-bottom: 12px;
    }

    h3 {
        font-size: 16px;
        margin-bottom: 8px;
    }

    p {
        font-size: 13.5px;
        line-height: 1.8;
        color: var(--nd-text-3);
    }
}

/* ================= 数字 ================= */
.stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--nd-gap-lg);
    text-align: center;
}

.stat {
    padding: 8px;

    &-value {
        font-size: 30px;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: var(--nd-primary-600);
        line-height: 1.2;
    }

    &-label {
        margin-top: 8px;
        font-size: 13.5px;
        color: var(--nd-text-3);
    }
}

/* ================= CTA ================= */
.cta-wrap {
    padding: 0 0 84px;
}

.cta {
    position: relative;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--nd-gap-xl);
    flex-wrap: wrap;
    padding: 46px 48px;
    border-radius: var(--nd-radius-xl);
    background: linear-gradient(120deg, #23857a 0%, #1c6b63 60%, #175450 100%);
    color: #fff;

    .cta-glow {
        position: absolute;
        width: 420px;
        height: 420px;
        top: -190px;
        right: -70px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.16) 0%, transparent 68%);
        pointer-events: none;
    }

    &-text {
        position: relative;
        z-index: 1;

        h2 {
            font-size: 26px;
            color: #fff;
            margin-bottom: 8px;
        }
        p {
            font-size: 14px;
            color: rgba(255, 255, 255, 0.76);
        }
    }

    &-actions {
        position: relative;
        z-index: 1;
        display: flex;
        gap: 12px;
        flex-wrap: wrap;

        :deep(.el-button) {
            height: 46px;
            padding: 0 24px;
        }
    }
}

/* 浅色底上的次要按钮 */
.ghost-btn {
    border-color: var(--nd-border-strong);
    background: transparent;
}

/* 深色块上的次要按钮需要白边 */
.cta-ghost {
    color: #fff;
    border-color: rgba(255, 255, 255, 0.45);
    background: transparent;

    &:hover {
        color: #fff;
        border-color: #fff;
        background: rgba(255, 255, 255, 0.12);
    }
}

/* ================= 响应式 ================= */
@media (max-width: 1080px) {
    .feature-grid,
    .steps {
        grid-template-columns: repeat(2, 1fr);
    }
}

@media (max-width: 900px) {
    .hero {
        padding: 48px 0 56px;
    }
    .hero-inner {
        grid-template-columns: 1fr;
        gap: var(--nd-gap-xl);
        text-align: center;
    }
    .hero-title {
        font-size: 34px;
    }
    .hero-desc {
        margin: 0 auto;
    }
    .hero-actions {
        justify-content: center;
    }
    .hero-trust {
        align-items: center;
    }
    .hero-art {
        height: 300px;
    }
    .art-card--chat {
        left: 0;
    }
    .art-card--mood {
        right: 0;
    }
}

@media (max-width: 640px) {
    .section {
        padding: 52px 0;
    }
    .feature-grid,
    .steps {
        grid-template-columns: 1fr;
    }
    .stats {
        grid-template-columns: repeat(2, 1fr);
        gap: var(--nd-gap);
    }
    .hero-title {
        font-size: 29px;
    }
    .cta {
        padding: 32px 24px;
    }
}
</style>
