<template>
    <div class="nd-logo" :class="[`nd-logo--${tone}`, { 'nd-logo--sm': size === 'sm' }]">
        <img class="nd-logo__mark" :src="iconUrl" alt="云舒" />
        <div v-if="!iconOnly" class="nd-logo__text">
            <span class="nd-logo__name">{{ title }}</span>
            <span v-if="subtitle" class="nd-logo__sub">{{ subtitle }}</span>
        </div>
    </div>
</template>

<script setup>
/**
 * 统一品牌区。
 * 原来 logo + 标题的写法散落在 5 个组件里（FrontendLayout / Sidebar / AuthLayout / ...），
 * 字号、间距、颜色各不相同，这里收敛成一处。
 */
const props = defineProps({
    title: { type: String, default: '云舒' },
    subtitle: { type: String, default: '' },
    /** dark：深色底上用（文字白色）；light：浅色底上用（文字深色） */
    tone: { type: String, default: 'light' },
    size: { type: String, default: 'md' },
    iconOnly: { type: Boolean, default: false }
})

const iconUrl = new URL('@/assets/images/机器人.png', import.meta.url).href
</script>

<style scoped>
.nd-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}

.nd-logo__mark {
    width: 40px;
    height: 40px;
    border-radius: var(--nd-radius-sm);
    object-fit: cover;
    flex: none;
    background: var(--nd-primary-50);
}

.nd-logo--sm .nd-logo__mark {
    width: 32px;
    height: 32px;
}

.nd-logo__text {
    display: flex;
    flex-direction: column;
    min-width: 0;
}

.nd-logo__name {
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.25;
    color: var(--nd-text-1);
    white-space: nowrap;
}

.nd-logo--sm .nd-logo__name {
    font-size: 16px;
}

.nd-logo__sub {
    font-size: 12px;
    line-height: 1.3;
    color: var(--nd-text-3);
    white-space: nowrap;
}

/* 深色背景（登录页左侧、页脚） */
.nd-logo--dark .nd-logo__name {
    color: #fff;
}
.nd-logo--dark .nd-logo__sub {
    color: rgba(255, 255, 255, 0.72);
}
.nd-logo--dark .nd-logo__mark {
    background: rgba(255, 255, 255, 0.14);
}
</style>
