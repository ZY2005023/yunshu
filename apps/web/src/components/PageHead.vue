<template>
    <div class="page-head">
        <div class="head-text">
            <p class="page-title">{{ props.title }}</p>
            <p v-if="props.subtitle" class="page-sub">{{ props.subtitle }}</p>
        </div>
        <div class="action-btn">
            <slot name="buttons"></slot>
        </div>
    </div>
</template>

<script setup>
/**
 * 管理端页面头部（knowledge / consultations / emotional / crisis / scaleRecords 共用）。
 *
 * 改版点：
 *  - 色值改走设计变量（原来写死 #2d3748）；
 *  - 新增可选副标题，方便说明这个页面在看什么；
 *  - 加一条分隔线，把「页头 / 筛选区 / 表格」三层结构交代清楚。
 */
const props = defineProps({
    title: {
        type: String,
        default: '页面标题'
    },
    subtitle: {
        type: String,
        default: ''
    }
})
</script>

<style lang="scss" scoped>
.page-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--nd-gap);
    flex-wrap: wrap;
    margin-bottom: var(--nd-gap-lg);
    padding-bottom: var(--nd-gap);
    border-bottom: 1px solid var(--nd-border);

    .page-title {
        font-size: 22px;
        font-weight: 600;
        line-height: 1.4;
        color: var(--nd-text-1);
    }

    .page-sub {
        margin-top: 4px;
        font-size: 13px;
        color: var(--nd-text-3);
    }

    .action-btn {
        flex: none;
        display: flex;
        align-items: center;
        gap: 10px;
    }
}
</style>
