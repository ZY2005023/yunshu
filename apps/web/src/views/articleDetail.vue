<template>
    <div class="articleDetail-container">
        <div class="header-section">
            <div class="nd-container header-content">
                <el-image :src="iconUrl" class="header-icon"></el-image>
                <div class="header-text">
                    <h1>知识文章</h1>
                    <p>{{ articleDetail.title || '正在加载…' }}</p>
                </div>
                <el-button class="back-btn" text @click="router.back()">
                    <el-icon><Back /></el-icon>
                    返回
                </el-button>
            </div>
        </div>
        <div class="content">
            <div class="diary-card">
                <p class="title">文章信息</p>
                <div class="sub-title">
                    <el-tag size="large" class="category-tag">{{ articleDetail.categoryName }}</el-tag>
                    <div class="flex-box">
                        <el-icon><List /></el-icon>
                        <span>{{ dayjs(articleDetail.updatedAt).format('YYYY-MM-DD') }}</span>
                    </div>
                </div>
                <h1 class="article-title">{{ articleDetail.title }}</h1>
                <div class="summary-content" v-if="articleDetail.summary ">
                    <p>{{ articleDetail.summary }}</p>
                </div>
                <div :style="{marginTop: '20px'}" class="flex-box">
                   <div class="item flex-box">
                        <el-icon><Avatar /></el-icon>
                        <span>{{ articleDetail.authorName }}</span>
                    </div>
                    <div class="item flex-box">
                        <el-icon><Platform /></el-icon>
                        <span>{{ articleDetail.readCount }} 次阅读</span>
                    </div>
                </div>
            </div>
            <div class="diary-card">
                <div class="title">正文内容</div>
                <div class="content-wrapper" v-html="sanitizeHtml(formatContent(articleDetail.content))"></div>
                <div class="tags-content" v-if="articleDetail.tagArray && articleDetail.tagArray.length">
                    <h4 class="tags-title"> 相关标签 </h4>
                    <div class="tags-list">
                        <el-tag v-for="tag in articleDetail.tagArray" :key="tag" type="info" effect="light" class="tag-item">{{ tag }}</el-tag>
                    </div>
                </div>
            </div>
            <!-- 读完的下一步：知识库文章是最安全的转化入口，别让用户读完就断头 -->
            <div class="diary-card article-cta">
                <p class="title">看完这篇文章，你还可以</p>
                <div class="cta-actions">
                    <el-button type="primary" round @click="router.push('/scale')">
                        <el-icon><DataLine /></el-icon>
                        做个心理测评
                    </el-button>
                    <el-button round @click="router.push('/consultation')">
                        <el-icon><ChatDotRound /></el-icon>
                        和 AI 聊聊
                    </el-button>
                </div>
            </div>
        </div>
    </div>
</template>
<script setup>
import { sanitizeHtml } from '@/utils/sanitize'
import { ref, onMounted } from 'vue'
import { getKnowledgeDetail } from '@/api/frontend'
import { dayjs } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()
import { Avatar } from '@element-plus/icons-vue'

const iconUrl = new URL('@/assets/images/book.png', import.meta.url).href

const props = defineProps({
    id: String
})

const articleDetail = ref({})

const formatContent = (content) => {
  if (!content) return ''
  
  // 基本的HTML清理和格式化
  let formatted = content
      .replace(/\n/g, '<br>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
  
  return formatted
}

onMounted(() => {
    getKnowledgeDetail(props.id).then(res => {
        articleDetail.value = res
    })
})
</script>

<style lang="scss" scoped>
.articleDetail-container {
    min-height: calc(100vh - var(--nd-navbar-h));
    background: var(--nd-bg);

    .flex-box {
        display: flex;
        align-items: center;
        .item {
            margin-right: 20px;
            span {
                margin-left: 5px;
            }
        }
    }

    /* 头部原来是与品牌无关的橙紫渐变，统一为品牌青绿 */
    .header-section {
        padding: 40px 0;
        color: #fff;
        background: linear-gradient(120deg, #23857a 0%, #1c6b63 60%, #175450 100%);

        .header-content {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .header-icon {
            flex: none;
            width: 56px;
            height: 56px;
        }

        .header-text {
            flex: 1;
            min-width: 0;

            h1 {
                font-size: 24px;
                color: #fff;
            }
            p {
                margin-top: 6px;
                font-size: 14px;
                color: rgba(255, 255, 255, 0.72);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
        }

        .back-btn {
            flex: none;
            padding: 8px 16px;
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.4);
            border-radius: var(--nd-radius-full);

            &:hover {
                color: #fff;
                background: rgba(255, 255, 255, 0.14);
            }
        }
    }

    .content {
        max-width: 900px;
        margin: 0 auto;
        padding: var(--nd-gap-lg) var(--nd-gap-lg) 48px;
    }

    .diary-card {
        margin-bottom: var(--nd-gap-lg);
        padding: 24px;
        background: var(--nd-surface);
        border: 1px solid var(--nd-border);
        border-radius: var(--nd-radius);
        box-shadow: var(--nd-shadow-xs);

        .title {
            margin-bottom: 16px;
            padding-left: 12px;
            border-left: 3px solid var(--nd-primary-500);
            font-size: 18px;
            font-weight: 600;
            color: var(--nd-text-1);
        }

        .sub-title {
            display: flex;
            align-items: center;
            gap: 16px;
            font-size: 13px;
            color: var(--nd-text-3);
        }

        .article-title {
            margin: 24px 0 14px;
            font-size: 26px;
            line-height: 1.4;
            color: var(--nd-text-1);
        }

        .summary-content {
            padding: 14px 18px;
            background: var(--nd-primary-50);
            border-left: 3px solid var(--nd-primary-400);
            border-radius: 0 var(--nd-radius-sm) var(--nd-radius-sm) 0;
            font-size: 14px;
            line-height: 1.85;
            color: var(--nd-text-2);
        }

        /* 正文排版：这是用户真正阅读的部分，行高与段距放松一些 */
        .content-wrapper {
            font-size: 15.5px;
            line-height: 1.95;
            color: var(--nd-text-2);

            :deep(p) {
                margin-bottom: 14px;
            }
            :deep(h1),
            :deep(h2),
            :deep(h3),
            :deep(h4),
            :deep(h5),
            :deep(h6) {
                margin: 22px 0 12px;
                font-weight: 600;
                color: var(--nd-text-1);
            }
            :deep(h2) {
                padding-bottom: 8px;
                font-size: 19px;
                border-bottom: 1px solid var(--nd-border);
            }
            :deep(h3) {
                font-size: 16px;
            }
            :deep(ul),
            :deep(ol) {
                margin-bottom: 14px;
                padding-left: 20px;
            }
            :deep(li) {
                margin-bottom: 6px;
                list-style: disc;
            }
            :deep(ol li) {
                list-style: decimal;
            }
            :deep(img) {
                margin: 12px 0;
                border-radius: var(--nd-radius-sm);
            }
            :deep(blockquote) {
                margin: 14px 0;
                padding: 12px 16px;
                background: var(--nd-surface-soft);
                border-left: 3px solid var(--nd-primary-300);
                color: var(--nd-text-3);
            }
        }

        .tags-content {
            margin-top: 22px;
            padding-top: 16px;
            border-top: 1px solid var(--nd-border);

            .tags-title {
                margin-bottom: 10px;
                font-size: 14px;
                font-weight: 600;
                color: var(--nd-text-2);
            }
            .tags-list {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }
        }

        /* 读完的下一步 —— 别让文章页成为断头路 */
        .article-cta {
            text-align: center;

            .title {
                margin-bottom: 14px;
                font-size: 15px;
                font-weight: 600;
                color: var(--nd-text-1);
            }
            .cta-actions {
                display: flex;
                justify-content: center;
                gap: 12px;
                flex-wrap: wrap;
            }
        }
    }
}

@media (max-width: 768px) {
    .articleDetail-container {
        .header-section .header-text p {
            display: none;
        }
        .content {
            padding: var(--nd-gap);
        }
        .diary-card {
            padding: 18px;

            .article-title {
                font-size: 21px;
            }
        }
    }
}
</style>