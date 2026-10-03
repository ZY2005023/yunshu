<template>
    <span class="nd-avatar" :style="sizeStyle" :title="name">
        <img v-if="src" :src="src" :alt="name" class="nd-avatar__img" />
        <span v-else class="nd-avatar__initial" :style="{ background: bg }">{{ initial }}</span>
    </span>
</template>

<script setup>
/**
 * 统一头像组件。
 *
 * 为什么不用 el-avatar + 外链占位图：
 *   1. 原来各页面写死了 `cube.elemecdn.com` 的占位图 —— 断网/内网环境会裂图；
 *   2. 那个占位图跟当前用户毫无关系，看不出「这是谁」。
 * 这里改为「有头像用头像，没有就用昵称首字 + 稳定色」，不依赖任何外网资源。
 */
import { computed } from 'vue'

const props = defineProps({
    name: { type: String, default: '' },
    src: { type: String, default: '' },
    size: { type: [Number, String], default: 34 },
    /** 用于稳定取色。同一个人每次都得到同一个颜色 */
    seed: { type: [String, Number], default: '' }
})

/** 首字：中文取第一个字，英文取首字母大写 */
const initial = computed(() => {
    const n = (props.name || '').trim()
    if (!n) return '心'
    const ch = n[0]
    return /[a-zA-Z]/.test(ch) ? ch.toUpperCase() : ch
})

/** 从品牌色阶里挑柔和配色，避免出现刺眼的高饱和色 */
const PALETTE = [
    'linear-gradient(135deg, #52b2a4, #23857a)',
    'linear-gradient(135deg, #7cc9bf, #2f9c8b)',
    'linear-gradient(135deg, #efab3c, #d98f22)',
    'linear-gradient(135deg, #5786e0, #3f68bd)',
    'linear-gradient(135deg, #2c9e6a, #1f7d52)',
    'linear-gradient(135deg, #dc5f5a, #b84843)'
]

const bg = computed(() => {
    const key = String(props.seed || props.name || '')
    let sum = 0
    for (let i = 0; i < key.length; i += 1) sum += key.charCodeAt(i)
    return PALETTE[sum % PALETTE.length]
})

const sizeStyle = computed(() => {
    const s = typeof props.size === 'number' ? `${props.size}px` : props.size
    return { width: s, height: s, fontSize: `calc(${s} * 0.42)` }
})
</script>

<style scoped>
.nd-avatar {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    border-radius: 50%;
    overflow: hidden;
    background: var(--nd-primary-100);
    box-shadow: 0 0 0 2px #fff, 0 0 0 3px var(--nd-border);
}

.nd-avatar__img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.nd-avatar__initial {
    width: 100%;
    height: 100%;
    display: grid;
    place-items: center;
    color: #fff;
    font-weight: 600;
    letter-spacing: 0;
    user-select: none;
}
</style>
