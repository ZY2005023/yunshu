<template>
    <div class="backend-layout">
        <el-container class="main-container">
            <Sidebar />
            <el-container class="right-container">
                <el-header class="layout-header">
                    <Navbar />
                </el-header>
                <el-main class="main-content">
                    <div class="content-container">
                        <router-view></router-view>
                    </div>
                </el-main>
            </el-container>
        </el-container>
    </div>
</template>

<script setup>
/**
 * 管理端布局。
 *
 * 改版要点：
 *  - 顶栏高度统一走 --nd-navbar-h，与用户端一致（原来写死 74px）；
 *  - 内容区改为「浅底 + 白色卡片」，让每个业务页成为一张独立卡片，视觉更清晰；
 *  - 显式设置 overflow，避免侧边栏与内容区各自出现滚动条。
 */
import Sidebar from './Sidebar.vue'
import Navbar from './Navbar.vue'
</script>

<style lang="scss" scoped>
.backend-layout {
    height: 100vh;
    overflow: hidden;
    background: var(--nd-bg);

    .main-container {
        height: 100%;
    }

    .right-container {
        /* flex 子项默认 min-height:auto 会导致内部滚动失效 */
        min-width: 0;
        min-height: 0;
    }

    .layout-header {
        height: var(--nd-navbar-h) !important;
        padding: 0 !important;
        flex: none;
        box-shadow: none;
        border-bottom: 1px solid var(--nd-border);
        background: var(--nd-surface);
    }

    .main-content {
        padding: 20px;
        background: var(--nd-bg);
        overflow-y: auto;
    }

    .content-container {
        min-height: 100%;
        padding: 22px;
        background: var(--nd-surface);
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius);
        box-shadow: var(--nd-shadow-xs);
    }
}

@media (max-width: 768px) {
    .main-content {
        padding: 12px;
    }
    .content-container {
        padding: 16px;
    }
}
</style>
