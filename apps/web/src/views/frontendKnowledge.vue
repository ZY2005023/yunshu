<template>
  <div class="knowledge-container">
    <div class="header-section">
        <div class="nd-container header-content">
            <el-image :src="iconUrl" class="header-icon"></el-image>
            <div class="header-text">
                <!-- 原标题误写为「情绪日志」（复制粘贴遗留），此处更正 -->
                <h1>心理健康知识库</h1>
                <p>先弄明白情绪、压力和人际是怎么回事，再决定怎么办</p>
            </div>
        </div>
    </div>
    <div class="content">
        <!-- 左侧菜单 -->
         <div class="recommend-section">
            <div class="section-title">推荐阅读</div>
            <div class="recommend-list">
                <div v-for="item in recommendList" :key="item.id" class="recommend-item" @click="goToArticle(item.id)">
                    <h4>{{item.title}}</h4>
                    <p class="read-count">
                        <el-icon><Histogram /></el-icon>
                            阅读量 {{ item.readCount }}
                    </p>
                </div>
            </div>
         </div>
         <!-- 右侧内容 -->
         <div class="article-list">
            <div v-for="item in articleList" :key="item.id" class="article-item" @click="goToArticle(item.id)">
                <el-image class="cover" fit="cover" :src="getImage(item.coverImage)"></el-image>
                <div class="info">
                    <div class="title">
                        <h3>{{ item.title }}</h3>
                        <el-tag plain type="primary" size="small">{{ item.categoryName }}</el-tag>
                    </div>
                    <div class="meta-row">
                        <div class="flex-box">
                            <el-icon><Avatar /></el-icon>
                            <span>{{ item.authorName }}</span>
                        </div>
                        <div class="flex-box">
                            <el-icon><List /></el-icon>
                            <span>{{ dayjs(item.updatedAt).format('YYYY-MM-DD') }}</span>
                        </div>
                        <div class="flex-box">
                            <el-icon><Platform /></el-icon>
                            <span>观看人数 {{ item.readCount }}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div v-if="!articleList.length" class="nd-empty">
                <span class="nd-empty-icon"><el-icon><Reading /></el-icon></span>
                <p>暂时还没有文章</p>
            </div>
         </div>
    </div>
    <!-- 分页 -->
    <div class="pagination-wrapper">
    <el-pagination 
        style="margin-top: 25px"
        :page-size="pagination.size"
        layout="prev, pager, next"
        :total="pagination.total"
        @change="handleChange" />
    </div>
  </div>
</template>
<script setup>
import { resolveFileUrl } from '@/config'
    import { dayjs } from 'element-plus'
    import { ref, reactive, onMounted } from 'vue'
    import { getKnowledgeList } from '@/api/frontend'
    import { useRouter } from 'vue-router'

    const router = useRouter()
    
    import iconUrl from '@/assets/images/book.png'
    import { Platform } from '@element-plus/icons-vue'

    // 推荐阅读列表
    const recommendList = ref([])

    // 右侧列表数据
    const pagination = reactive({
        currentPage: 1,
        size: 10,
        total: 0
    })

    const articleList = ref([])
    // 获取列表数据
    const getPageList = () => {
        const params = {
            sortField: 'publishedAt',
            sortDirection: 'desc',
            ...pagination
        }
        getKnowledgeList(params).then(res => {
            articleList.value = res.records
            pagination.total = res.total
        })
    }
    // 获取封面图片
    const getImage = (url) => {
        return url ? resolveFileUrl(url) : 'https://file.itndedu.com/psychology_ai.png'
    }

    const handleChange = (page) => {
        pagination.currentPage = page
        getPageList()
    }

    // 跳转到详情
    const goToArticle = (id) => {
        router.push(`/knowledge/article/${id}`)
    }

    onMounted(() => {
        // 获取推荐阅读列表
        const params = {
            sortField: 'readCount',
            sortDirection: 'desc',
            currentPage: 1,
            size: 5
        }
        getPageList()
        getKnowledgeList(params).then(res => {
            // console.log(res)
            recommendList.value = res.records
        })
    })
</script>
<style lang="scss" scoped>
.knowledge-container {
    background: var(--nd-bg);
    min-height: calc(100vh - var(--nd-navbar-h));

    .flex-box {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* 头部原来是与品牌无关的橙紫渐变，统一为品牌青绿 */
    .header-section {
        background: linear-gradient(120deg, #23857a 0%, #1c6b63 60%, #175450 100%);
        color: #fff;
        padding: 44px 0;

        .header-content {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .header-icon {
            width: 56px;
            height: 56px;
            flex: none;
        }
        .header-text {
            h1 {
                font-size: 26px;
                color: #fff;
            }
            p {
                margin-top: 6px;
                font-size: 14px;
                color: rgba(255, 255, 255, 0.72);
            }
        }
    }

    .content {
        display: flex;
        align-items: flex-start;
        gap: var(--nd-gap-lg);
        max-width: var(--nd-container);
        margin: 0 auto;
        padding: var(--nd-gap-lg);
    }

    .recommend-section {
        flex: none;
        width: 280px;
        padding: 18px;
        background: var(--nd-surface);
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius);
        box-shadow: var(--nd-shadow-xs);

        .section-title {
            margin-bottom: 14px;
            font-size: 14px;
            font-weight: 600;
            color: var(--nd-text-1);
        }

        .recommend-list {
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .recommend-item {
            padding-left: 10px;
            border-left: 3px solid var(--nd-primary-400);
            cursor: pointer;

            h4 {
                font-size: 14px;
                line-height: 1.5;
                font-weight: 500;
                color: var(--nd-text-2);
                transition: color var(--nd-duration) var(--nd-ease);
            }

            &:hover h4 {
                color: var(--nd-primary-600);
            }

            .read-count {
                display: flex;
                align-items: center;
                gap: 6px;
                margin-top: 8px;
                font-size: 12px;
                color: var(--nd-text-4);
            }
        }
    }

    .article-list {
        flex: 1;
        min-width: 0;

        .article-item {
            display: flex;
            gap: 18px;
            margin-bottom: var(--nd-gap);
            padding: 16px;
            background: var(--nd-surface);
            border: 1px solid var(--nd-border);
            border-radius: var(--nd-radius);
            box-shadow: var(--nd-shadow-xs);
            cursor: pointer;
            transition:
                transform var(--nd-duration) var(--nd-ease),
                box-shadow var(--nd-duration) var(--nd-ease),
                border-color var(--nd-duration) var(--nd-ease);

            &:hover {
                transform: translateY(-2px);
                box-shadow: var(--nd-shadow);
                border-color: var(--nd-primary-200);
            }

            .cover {
                flex: none;
                width: 220px;
                height: 140px;
                border-radius: var(--nd-radius-sm);
                overflow: hidden;
            }

            .info {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;

                .title {
                    display: flex;
                    align-items: center;
                    gap: 10px;

                    h3 {
                        font-size: 17px;
                        line-height: 1.45;
                    }
                }

                .meta-row {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px 18px;
                    margin-top: auto;
                    padding-top: 12px;
                    font-size: 12.5px;
                    color: var(--nd-text-3);
                }
            }
        }
    }

    .pagination-wrapper {
        display: flex;
        justify-content: center;
        padding-bottom: 36px;
    }
}

@media (max-width: 900px) {
    .knowledge-container {
        .content {
            flex-direction: column;
        }
        .recommend-section {
            width: 100%;
        }
        .article-list .article-item {
            flex-direction: column;

            .cover {
                width: 100%;
                height: 180px;
            }
        }
    }
}
</style>
