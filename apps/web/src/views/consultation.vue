<template>
    <div class="consultation-container">
        <div class="sidebar">
            <!-- AI助手信息 -->
             <div class="ai-assistant-info">
                <div class="breathing-circle">
                    <el-image :src="iconUrl" style="width: 25px;height:25px" alt="AI助手" />
                </div>
                <h3 class="assistant-name">云舒AI助手</h3>
                <div class="online-status">
                    <div class="status-dot"></div>
                    在线服务中
                </div>
             </div>
             <!-- 情绪花园 -->
             <div class="emotion-garden">
                <div class="garden-header">
                    <div class="garden-title"> 情绪花园 </div>
                </div>
                <div class="emotion-info">
                    <div class="emotion-name">中性</div>
                    <div class="emotion-score">50</div>
                </div>
                <div class="warm-tips">
                    <div class="emotion-status-text">
                        <span class="status-label">今天感觉</span>
                        <span class="status-emotion">{{ currentEmotion.isNegative ? '需要关注' : '很不错' }}</span>
                    </div>
                    <div class="emotion-intensity">
                        <span class="intensity-dots">
                            <span v-for="dot in 3" :key="dot" class="dot" :class="{'active': getIntensityClass(currentEmotion.emotionScore) >= dot}"></span>
                        </span>
                        <span class="intensity-text">
                            {{ getRiskText(currentEmotion.riskLevel) }}
                        </span>
                    </div>
                    <!-- 温暖建议卡片 -->
                     <div class="warm-suggestion" v-if="currentEmotion.suggestion">
                        <div class="suggestion-icon">💝</div>
                        <div class="suggestion-content">
                            <div class="suggestion-title">给你的小建议</div>
                            <div class="suggestion-text">{{ currentEmotion.suggestion }}</div>
                        </div>
                     </div>
                     <!-- 治愈行动 -->
                      <div class="healing-actions" v-if="currentEmotion.improvementSuggestions.length > 0">
                        <div class="actions-title">治愈小行动</div>
                        <div class="actions-list">
                            <div v-for="action in currentEmotion.improvementSuggestions" :key="action" class="action-item">
                                <div class="action-icon">✨</div>
                                <div class="action-text">{{ action }}</div>
                            </div>
                        </div>
                      </div>
                      <!-- 风险提示 -->
                    <div class="risk-notice" v-if="currentEmotion.isNegative && currentEmotion.riskLevel > 1">
                        <div class="notice-icon">🤗</div>
                        <div class="notice-content">
                            <div class="notice-title">温馨提示</div>
                            <div class="notice-text">{{ currentEmotion.riskDescription }}</div>
                        </div>
                    </div>
                </div>
             </div>
             <!-- 会话列表 -->
             <div class="session-history">
                <h4 class="section-title">会话列表</h4>
                <div class="session-list">
                    <div
                        v-for="session in sessionList"
                        :key="session.id"
                        @click="handleSessionClick(session)"
                        class="session-item"
                        :class="{ active: currentSession && currentSession.sessionId === 'session_' + session.id }"
                    >
                        <div class="session-info">
                            <div class="session-title">
                                <span>{{ session.sessionTitle }}</span>
                                <div class="session-meta">
                                    <span class="session-time">{{ session.startedAt }}</span>
                                </div>
                                <div class="session-preview">
                                    {{ session.lastMessageContent }}
                                </div>
                                <div class="session-stats">
                                    <span>
                                        <el-icon>
                                            <ChatRound />
                                        </el-icon>
                                        {{ session.messageCount || 0 }}
                                    </span>
                                    <span>
                                        <el-icon>
                                            <Clock />
                                        </el-icon>
                                        {{ session.durationMinutes || 0 }} 分钟
                                    </span>
                                </div>
                            </div>
                            <div class="session-actions">
                                <el-button text type="danger" size="mini" @click="handleDeleteSession(session.id)">
                                    <el-icon>
                                        <DeleteFilled />
                                    </el-icon>
                                </el-button>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- 会话分页：此前写死只取第一页，第 11 个会话永远够不到 -->
                <el-pagination
                    v-if="sessionPagination.total > sessionPagination.size"
                    :current-page="sessionPagination.currentPage"
                    :page-size="sessionPagination.size"
                    :total="sessionPagination.total"
                    layout="prev, pager, next"
                    :pager-count="5"
                    small
                    class="session-pager"
                    @current-change="handleSessionPageChange"
                />
             </div>
        </div>
        <div class="chat-main">
            <div class="chat-header">
                <div class="header-left">
                    <div class="chat-avatar">
                        <el-image :src="iconUrl1" style="width: 30px;height: 30px" />
                    </div>
                    <div class="chat-info">
                        <h2>云舒AI助手</h2>
                        <p>您的贴心AI心理健康助手</p>
                    </div>
                </div>
                <el-button circle @click="createNewFrontendSession" title="新建会话">
                    <el-icon>
                        <Plus />
                    </el-icon>
                </el-button>
            </div>
            <!-- 聊天消息区域 -->
            <div class="chat-messages">
                <!-- 欢迎用语 -->
                <div class="message-item ai-message" v-if="messages.length === 0">
                    <div class="message-avatar">
                        <el-image :src="iconUrl" style="width: 18px;height: 18px" />
                    </div>
                    <div class="message-content">
                        <div class="message-bubble">
                            <p>您好！我是小暖，您的AI心理健康助手。很高兴陪伴您，为您提供温暖的心理支持。请告诉我，今天您感觉怎么样？有什么想要分享的吗？</p>
                        </div>
                        <div class="message-time">刚刚</div>
                    </div>
                </div>
                <!-- 消息列表 -->
                <div v-for="msg in messages" :key="msg.id" class="message-item" :class="msg.senderType === 1 ?  'user-message' : 'ai-message'">
                    <div class="message-avatar">
                        <el-image v-if="msg.senderType === 1" style="width: 18px; height:18px" :src="iconUrl2"></el-image>
                        <el-image v-if="msg.senderType === 2" style="width: 18px; height:18px" :src="iconUrl"></el-image>
                    </div>
                    <div class="message-content">
                        <div class="message-bubble">
                            <!-- AI正在思考中 -->
                            <div v-if="msg.senderType === 2 && isAiTyping && !msg.content" class="typing-indicator">
                                <div class="typing-dot"></div>
                                <div class="typing-dot"></div>
                                <div class="typing-dot"></div>
                            </div>
                            <!-- AI错误提示 -->
                            <div v-else-if="msg.isError" class="error-message">
                                <p>{{ msg.content }}</p>
                            </div>
                            <!-- AI正常返回消息 -->
                             <MarkdownRenderer v-else-if="msg.senderType === 2 && !msg.isError" :content="msg.content" :is-ai-message="true" />
                             <p v-else-if="msg.content" v-html="formatMessageContent(msg.content)"></p>
                        </div>
                        <div class="message-time">{{ msg.senderType === 2 && isAiTyping ? '正在输入中...' : msg.createdAt }}</div>
                    </div>
                </div>
                <!-- 危机求助卡片：固定在消息区底部，不会被 AI 回复顶掉 -->
                <div v-if="currentAgent" class="agent-bar">
                    <span class="agent-label">{{ currentAgent.label }}</span>
                    <span class="agent-hint">{{ agentHint(currentAgent.agent) }}</span>
                    <!-- 提示要能落地：说到测评就给测评入口，别让引导停在文字上 -->
                    <el-button
                        v-if="currentAgent.agent === 'ASSESSMENT'"
                        text
                        type="primary"
                        size="small"
                        @click="router.push('/scale')"
                    >
                        去做测评<el-icon><Right /></el-icon>
                    </el-button>
                </div>
                <div v-if="sources.length" class="sources-bar">
                    <span class="sources-label">参考来源</span>
                    <el-tag v-for="s in sources" :key="s.articleId" size="small" type="info"
                        class="source-tag" @click="openArticle(s.articleId)">
                        {{ s.title }}
                    </el-tag>
                </div>
                <div v-if="crisisCard" class="crisis-card">
                    <div class="crisis-header">
                        <span class="crisis-icon">🤝</span>
                        <span class="crisis-title">{{ crisisCard.title }}</span>
                    </div>
                    <div class="crisis-subtitle">{{ crisisCard.subtitle }}</div>
                    <ul class="crisis-lines">
                        <li v-for="line in crisisCard.helplines" :key="line">{{ line }}</li>
                    </ul>
                    <div class="crisis-disclaimer">{{ crisisCard.disclaimer }}</div>
                    <el-button size="small" text @click="crisisCard = null">我知道了</el-button>
                </div>
            </div>
            <!-- 常驻免责声明：心理类产品必须明确边界 -->
            <div class="disclaimer-bar">
                本系统由 AI 提供内容支持，不能替代专业心理诊疗或医疗诊断；如遇紧急情况请立即拨打 120 / 110。
            </div>
            <!-- 消息输入区域 -->
            <div class="chat-input">
                <div class="input-container">
                    <el-input
                        v-model="userMessage"
                        placeholder="请输入您想要分享的内容..."
                        type="textarea"
                        :rows="3"
                        :disabled="isAiTyping"
                        @keydown="handleKeyDown"
                        class="message-input"
                        clearable />
                        <div class="input-footer">
                            <span>按Enter发送，Shift+Enter换行</span>
                            <span>{{ userMessage.length }}/500</span>
                        </div>
                </div>
                <el-button :disabled="!userMessage.trim() || userMessage.length > 500" type="primary" class="send-btn" @click="sendMessage">
                    <el-icon>
                        <Promotion />
                    </el-icon>
                </el-button>
            </div>
        </div>
    </div>
</template>
<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { startSession, getSessionList, deleteSession, getSessionDetail, getSessionEmotion } from '@/api/frontend'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatRound, DeleteFilled } from '@element-plus/icons-vue'
import MarkdownRenderer from '@/components/MarkdownRenderer.vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { escapeHtml } from '@/utils/sanitize'
import { refreshTokenSilently, clearAuthAndRedirect } from '@/utils/request'
import { DEFAULT_EMOTION_STATE, normalizeEmotionState } from '@/utils/sessionEmotion'

import { useRouter } from 'vue-router'

const router = useRouter()

/** 点参考来源跳到文章详情 —— 让用户能查证答案依据 */
const openArticle = (id) => {
    if (id) router.push(`/knowledge/article/${id}`)
}

/** 各 Agent 的说明文案，让用户知道系统为什么这样应答 */
const AGENT_HINTS = {
    CRISIS: '已优先保障你的安全，请留意下方求助信息',
    ASSESSMENT: '可以到「心理测评」做一次标准化自评',
    REFERRAL: '想找人聊聊的话，这些渠道都可以',
    RESOURCE: '为你整理了相关资料',
    INFO: '为你解答'
}
const agentHint = (code) => AGENT_HINTS[code] || ''

const iconUrl = new URL('@/assets/images/robot-fill.png', import.meta.url).href
const iconUrl1 = new URL('@/assets/images/like.png', import.meta.url).href
const iconUrl2 = new URL('@/assets/images/users.png', import.meta.url).href

// 新建会话
const createNewFrontendSession = () => {
    // 创建一个新的会话对象
    const newSession = {
        sessionId: `temp_${Date.now()}`,
        status: 'TEMP',
        sessionTitle: '新对话'
    }
    currentSession.value = newSession
}

// 定义一个当前会话对象
const currentSession = ref(null)
const sessionList = ref([])
// 会话列表分页状态（后端接口本就支持，前端此前没接）
const sessionPagination = reactive({ currentPage: 1, size: 10, total: 0 })

// 定义对话消息
const messages = ref([])
// 定义用户输入消息
const userMessage = ref('')
// 定义AI助手是否正在输入
const isAiTyping = ref(false)

// 危机求助卡片（由后端 crisis 事件下发，固定在消息区，不会被 AI 回复覆盖）
const crisisCard = ref(null)

/** RAG 检索到的参考来源（本次回答依据的知识库文章） */
const sources = ref([])

/** 本轮由哪类 Agent 应答（意图路由结果） */
const currentAgent = ref(null)

// SSE 请求的中止控制：组件卸载或发起新请求前必须中止，否则会泄漏连接
let streamCtrl = null
// 主动掐断的流不算「AI回复失败」—— 切换会话/离开页面时不应弹错误提示
let streamAbortedLocally = false
const abortStream = () => {
    if (streamCtrl) {
        streamAbortedLocally = true
        try {
            streamCtrl.abort()
        } catch (e) {
            // 已中止，忽略
        }
        streamCtrl = null
    }
}

// 情绪花园（初始值与归一化逻辑统一走 utils/sessionEmotion.js，见其顶部的事故说明）
const currentEmotion = ref({ ...DEFAULT_EMOTION_STATE })

const loadSessionEmotion = (sessionId) => {
   // 确保sessionID格式正确
    const id = sessionId.toString().startsWith('session_') ? sessionId : `session_${sessionId}`

    getSessionEmotion(id).then(res => {
        // ⚠️ 不能把接口返回原样赋进来：响应形状是 {sessionId, emotionAnalysis}，
        //    模板要的是扁平的花园状态 —— 必须经 normalizeEmotionState 归一化，
        //    否则 improvementSuggestions 变 undefined，渲染直接中断。
        currentEmotion.value = normalizeEmotionState(res)
    })
}

const getIntensityClass = (score) => {
    if (score >= 61) {
        return 3
    }
    if (score >= 31) {
        return 2
    }
    return 1
}

const getRiskText = (level) => {
    switch (level) {
        case 0:
            return '正常'
        case 1:
            return '关注'
        case 2:
            return '预警'
        case 3:
            return '危机'
        default:
            return '正常'
    }
}

// 定义处理键盘事件
const handleKeyDown = (e) => {
    // 中文输入法选词中的 Enter（isComposing / keyCode 229）不发送 ——
    // 不然拼音还没上屏消息就飞出去了，中文产品的高频误触
    if (e.isComposing || e.keyCode === 229) return
    // 与界面提示保持一致：Enter 发送，Shift+Enter 换行
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        sendMessage()
    }
}

// 用户发送消息
const sendMessage = () => {
    if (!userMessage.value.trim()) return

    if (isAiTyping.value) {
        ElMessage.error('AI助手正在输入中，请稍后')
        return
    }

    const message = userMessage.value.trim()
    userMessage.value = ''

    // 如果没有会话或者是临时会话，就需要创建一个新的会话
    if (currentSession.value.status === 'TEMP') {
       startNewSession(message)
    } else {
        // 继续现有会话
        messages.value.push({
            id: Date.now(),
            senderType: 1,
            content: message,
            createAt: new Date().toISOString()
        })
        startAIResponse(currentSession.value.sessionId, message)
    }
}

const startNewSession = (message) => {
    // 构建会话参数
    const sessionParams = {
        initialMessage: message
    }
    if (currentSession.value.sessionTitle === '新对话') {
        sessionParams.sessionTitle = `云舒AI助手 - ${new Date().toLocaleString()}`
    } else {
        // 如果历史会话记录
        sessionParams.sessionTitle = currentSession.value.sessionTitle
    }
    // 调用后端接口创建新会话
    startSession(sessionParams).then(res => {
       // 将后端返回的数据转为前端会话格式
       const sessionData = {
            sessionId: res.sessionId,
            status: res.status,
            sessionTitle: sessionParams.sessionTitle
       }
       // 如果当前是临时会话，更新数据
       if (currentSession.value && currentSession.value.status === 'TEMP') {
            // 更新为正式会话 
            Object.assign(currentSession.value, sessionData)
       } else {
            // 否则，创建一个新的会话
            currentSession.value = sessionData
       }
       // 更新会话列表：新会话置顶，回第一页
       getSessionPage(1)

       // 添加初始用户消息
       messages.value.push({
        id: Date.now(),
        senderType: 1,
        content: message,
        createAt: new Date().toISOString()
       })

       // 开始流式对话
       startAIResponse(currentSession.value.sessionId, message)
    })
}

const startAIResponse = (sessionId, userMessage) => {
    // 每次提问重置来源与本轮路由结果，避免上一轮的残留在下面
    sources.value = []
    currentAgent.value = null
    // 防止重复发送
    if (isAiTyping.value) {
        ElMessage.error('AI助手正在输入中，请稍后')
        return
    }

    
    isAiTyping.value = true

    const aiMessage = {
        id: `ai_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        senderType: 2,
        content: '',
        createAt: new Date().toISOString()
    }
    messages.value.push(aiMessage)

    // 调用流式接口（鉴权统一走 Authorization: Bearer）
    // attempt() 可重入：401 时静默续期，带着新 token 重新发起（只重试一次）
    let tokenRetried = false
    const attempt = () => {
        abortStream() // 先掐掉可能残留的旧流（重试路径上由 onerror 先行清理过）
        streamCtrl = new AbortController()
        streamAbortedLocally = false
    fetchEventSource('/api/psychological-chat/stream', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + (localStorage.getItem('token') || ''),
            'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
            sessionId,
            userMessage
        }),
        signal: streamCtrl.signal,
        onopen: async (response) => {
            // ⚠️ SSE 不走 axios 拦截器 —— access token 过期时后端回 401 + JSON，
            // 此前用户只会看到「AI回复失败」。现在先静默续期一次再重试。
            if (response.status === 401 && !tokenRetried) {
                tokenRetried = true
                try {
                    await refreshTokenSilently()
                } catch (e) {
                    // refresh token 也没了：跳登录（与 axios 401 行为一致）
                    clearAuthAndRedirect()
                    throw new Error('__ND_STOP__')
                }
                setTimeout(attempt, 0)
                throw new Error('__ND_STOP__')
            }
            const ctype = response.headers.get('Content-Type') || ''
            if (!ctype.includes('text/event-stream')) {
                // 登录失效等情况会返回 JSON 而非流，交给错误分支统一处理
                throw new Error('服务器返回非流式数据')
            }
        },
        onmessage: (event) => {
            const raw = (event.data || '').trim()
            if (!raw) return
            const eventName = event.event
            // 当前会话的AI消息
            const aiMessage = messages.value[messages.value.length - 1]

            // 危机求助卡片：先于 AI 回复下发，独立于 AI 内容，不会被覆盖
            if (eventName === 'crisis') {
                try {
                    const card = JSON.parse(raw)
                    if (String(card.code) === '200') {
                        crisisCard.value = card.data
                    }
                } catch (e) {
                    // 解析失败则忽略，不阻塞对话
                }
                return
            }

            // 意图路由结果：本轮由哪类 Agent 应答
            if (eventName === 'agent') {
                try {
                    const payload = JSON.parse(raw)
                    if (String(payload.code) === '200' && payload.data) {
                        currentAgent.value = payload.data
                    }
                } catch (e) {
                    // 解析失败忽略
                }
                return
            }

            // 参考来源：知识库命中的文章，早于正文下发
            if (eventName === 'sources') {
                try {
                    const payload = JSON.parse(raw)
                    if (String(payload.code) === '200' && payload.data) {
                        sources.value = payload.data.sources || []
                    }
                } catch (e) {
                    // 解析失败忽略，不影响对话
                }
                return
            }

            if (eventName === 'done') {
                isAiTyping.value = false
                abortStream()
                loadSessionEmotion(currentSession.value.sessionId)
                return
            }

            let payload
            try {
                payload = JSON.parse(raw)
            } catch (e) {
                return
            }
            if (String(payload.code) !== '200') {
                handleError(payload.msg || 'AI回复失败')
                return
            }
            if (payload.data && payload.data.content && aiMessage) {
                aiMessage.content += payload.data.content
            }
        },
        onerror: (err) => {
            // 静默续期路径的退出信号：不发「AI回复失败」，也不当主动掐断
            if (err && err.message === '__ND_STOP__') {
                abortStream()
                throw err
            }
            // 主动掐断（切换会话 / 离开页面）不是失败，静默收场即可，
            // 否则用户只是点了下别的会话，屏幕上却弹出「AI回复失败」
            if (streamAbortedLocally) {
                streamAbortedLocally = false
                isAiTyping.value = false
                streamCtrl = null
                return
            }
            // 必须在这里复位状态，否则输入框会被永久禁用
            handleError('AI回复失败，请重试')
            abortStream()
            throw err
        },
        onclose: () => {
            // 无论正常还是异常关闭，都要复位状态
            isAiTyping.value = false
            if (currentSession.value && currentSession.value.sessionId) {
                loadSessionEmotion(currentSession.value.sessionId)
            }
        }
        }).catch(() => {
            // 库的失败都已路由进 onerror（UI 处理完毕），这里吞掉拒绝避免噪音
        })
    }

    attempt()
}

// 错误处理函数
const handleError = (error) => {
    // 当前会话的AI消息（只替换还没吐出内容的占位消息，避免覆盖已收到的部分）
    const aiMessage = messages.value[messages.value.length - 1]
    if (aiMessage && aiMessage.senderType === 2 && !aiMessage.content) {
        aiMessage.content = error || 'AI回复失败，请重试'
    }
    isAiTyping.value = false
    abortStream()
    ElMessage.error(error || 'AI回复失败，请重试')
}

const getSessionPage = (page) => {
    // 会话分页 —— 之前写死 currentPage:1/size:10，第 11 个会话永远够不到
    if (page) sessionPagination.currentPage = page
    getSessionList({
        currentPage: sessionPagination.currentPage,
        size: sessionPagination.size
    }).then(res => {
        sessionList.value = res.records || []
        sessionPagination.total = res.total || 0
    })
}

const handleSessionPageChange = (page) => {
    getSessionPage(page)
}

// 获取会话数据（点击会话列表加载历史消息到对话窗）
const handleSessionClick = (session) => {
    // ⚠️ 流式进行中切换会话必须先掐断旧流：onmessage 往「当前 messages 数组
    //    的最后一条」追加内容 —— 不掐断的话，AI 回复会写进新会话的消息列表里，
    //    isAiTyping 也会卡在 true（输入框被禁用）、情绪花园被旧会话的回调覆盖。
    abortStream()
    isAiTyping.value = false
    currentAgent.value = null
    sources.value = []

    // 点击会话时，获取会话详情（拦截器已剥层: {sessionId, messages}）
    getSessionDetail(session.id).then(res => {
        messages.value = (res && res.messages) ? res.messages : []
    })
    loadSessionEmotion(session.id)
    // 更新当前会话对象数据
    const sessionData = {
        sessionId: "session_" + session.id,
        status: 'ACTIVE',
        sessionTitle: session.sessionTitle
    }
    currentSession.value = sessionData
}

const handleDeleteSession = (sessionId) => {
    // 删除不可恢复（心理健康对话，误触代价高），必须二次确认
    ElMessageBox.confirm('删除后该会话的全部聊天记录将无法恢复。确定删除吗？', '删除会话', {
        confirmButtonText: '删除',
        cancelButtonText: '再想想',
        type: 'warning'
    })
        .then(() => {
            deleteSession(sessionId).then(res => {
                ElMessage.success('删除成功')
                // 当前页只剩这一条且不在第一页时回退一页，避免停在空页上
                if (sessionList.value.length <= 1 && sessionPagination.currentPage > 1) {
                    sessionPagination.currentPage -= 1
                }
                getSessionPage()
            })
        })
        .catch(() => {
            // 取消：什么也不做
        })
}

// 用户消息渲染：先转义再换行，避免把自己的输入当 HTML 执行
const formatMessageContent = (content) => {
    return escapeHtml(content || '').replace(/\n/g, '<br>')
}

onMounted(() => {
    // 初始化时获取会话列表
    getSessionPage()
    // 初始化时创建一个新会话
    createNewFrontendSession()
})

// 离开页面时中止未完成的流，避免连接与内存泄漏
onUnmounted(() => {
    abortStream()
})
</script>
<style scoped lang="scss">
.consultation-container {
    /* 原为固定 width: 1200px，小屏会横向溢出，改为弹性上限 */
    max-width: 1200px;
    width: 100%;
    margin: 0 auto;
    display: flex;
    gap: 20px;
    padding: 20px;
    /* 一屏展示：视口高度减去导航栏高度，两栏各自内部滚动 */
    /* 顶栏高度改为与全局一致的 --nd-navbar-h（原写死 105px，改版后对不上会多出空白） */
    height: calc(100vh - var(--nd-navbar-h));
    min-height: 560px;
    box-sizing: border-box;
    overflow: hidden;
    .sidebar {
        width: 300px;
        height: 100%;
        overflow-y: auto;
        flex-shrink: 0;
        display: flex;
        flex-direction: column;
        scrollbar-width: thin;
        .ai-assistant-info {
            margin-bottom: 12px;
            background: var(--nd-surface);
            border-radius: var(--nd-radius);
            padding: 14px 12px;
            box-shadow: var(--nd-shadow-xs);
            border: 1px solid var(--nd-border);
            transition: all 0.3s ease;
            flex-shrink: 0;
            .breathing-circle {
                width: 44px;
                height: 44px;
                /* 原为橙色系，与品牌青绿冲突，统一为主色 */
                background: linear-gradient(135deg, var(--nd-primary-400) 0%, var(--nd-primary-600) 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 12px;
                animation: breathing 4s ease-in-out infinite;
                box-shadow: 0 6px 24px rgba(47, 156, 139, 0.25);
                position: relative;
            }
            .assistant-name {
                font-size: 15px;
                font-weight: 700;
                background: linear-gradient(135deg, var(--nd-primary-500), var(--nd-primary-700));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                text-align: center;
                background-clip: text;
                margin: 0 0 6px;
            }
            .online-status {
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--nd-success);
                font-size: 12px;
                font-weight: 600;
                .status-dot {
                    width: 8px;
                    height: 8px;
                    background: var(--nd-success);
                    border-radius: 50%;
                    margin-right: 8px;
                    animation: pulse 2s infinite;
                    box-shadow: 0 0 8px rgba(44, 158, 106, 0.4);
                }
            }
        }
        .session-history {
            background: white;
            border-radius: 16px;
            padding: 14px;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
            margin-bottom: 0;
            flex: 1;
            min-height: 160px;
            display: flex;
            flex-direction: column;
            .section-title {
                font-size: 15px;
                font-weight: 600;
                color: #333;
                margin: 0 0 10px;
                display: flex;
                align-items: center;
                justify-content: space-between;

            }
            .session-list {
                overflow-y: auto;
                flex: 1;
                min-height: 0;
                scrollbar-width: thin;
                scrollbar-color: rgba(64, 150, 255, 0.3) transparent;
                .session-item {
                    position: relative;
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                    padding: 12px;
                    margin-bottom: 8px;
                    border-radius: 12px;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    border: 2px solid transparent;
                    &:hover {
                        background: #f8f9ff;
                        border-color: #e6f0ff;
                    }
                    &.active {
                        background: #e6f0ff;
                        border-color: #4096ff;
                    }
                    .session-info {
                        flex: 1;
                        .session-title {
                            font-weight: 500;
                            font-size: 14px;
                            color: #333;
                            margin-bottom: 4px;
                            white-space: nowrap;
                            overflow: hidden;
                            text-overflow: ellipsis;
                            .session-meta {
                                display: flex;
                                align-items: center;
                                gap: 8px;
                                margin-bottom: 6px;
                                .session-time {
                                    font-size: 12px;
                                    color: #999;
                                }
                            }
                            .session-preview {
                                width: 200px;
                                font-size: 12px;
                                color: #666;
                                margin-bottom: 6px;
                                white-space: nowrap;
                                overflow: hidden;
                                text-overflow: ellipsis;
                            }
                            .session-stats {
                                display: flex;
                                align-items: center;
                                gap: 12px;
                                span {
                                    font-size: 12px;
                                    color: #999;
                                    display: flex;
                                    align-items: center;
                                    gap: 4px;
                                }
                            }
                        }
                        .session-actions {
                            position: absolute;
                            top: 10px;
                            right: 12px;
                        }
                    }
                }
                .no-sessions-text {
                    text-align: center;
                    font-size: 14px;
                    color: #999;
                }
            }
            .session-pager {
                flex-shrink: 0;
                justify-content: center;
                padding: 8px 0 2px;
                :deep(.el-pager li),
                :deep(.btn-prev),
                :deep(.btn-next) {
                    background: transparent;
                }
            }
        }
        .emotion-garden {
            background: linear-gradient(135deg, var(--nd-surface-soft) 0%, #fcf4e6 50%, #f6f0e8 100%);
            border-radius: 20px;
            padding: 14px;
            margin-bottom: 12px;
            box-shadow: 0 8px 32px rgba(252, 244, 230, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
            flex-shrink: 0;
            
            .garden-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 20px;
                position: relative;
                z-index: 2;
                .garden-title {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 16px;
                    font-weight: 600;
                    color: #8b4513;
                }
            }
            .emotion-info {
                margin: 0 auto;
                width: 80px;
                height: 80px;
                border-radius: 50%;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                z-index: 10;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
                border: 2px solid rgba(255, 255, 255, 0.8);
                background: linear-gradient(135deg, var(--nd-primary-300) 0%, var(--nd-primary-100) 50%, var(--nd-primary-100) 100%);
                color: #fff;
                .emotion-name {
                    font-size: 15px;
                    font-weight: 600;
                    line-height: 1;
                    margin-bottom: 2px;
                }
                .emotion-score {
                    font-size: 14px;
                    font-weight: 700;
                    opacity: 0.9;
                }
            }
            .warm-tips {
                text-align: center;
                margin-bottom: 16px;
                .emotion-status-text {
                    margin-bottom: 12px;
                    .status-label {
                        font-size: 14px;
                        color: var(--nd-text-2);
                        margin-right: 8px;
                    }
                    .status-emotion {
                        font-size: 16px;
                        font-weight: 600;
                        padding: 4px 12px;
                        border-radius: 16px;
                        display: inline-block;
                    }
                }
                .emotion-intensity {
                    margin-bottom: 16px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    .intensity-dots {
                        display: flex;
                        gap: 4px;
                        .dot {
                            width: 8px;
                            height: 8px;
                            border-radius: 50%;
                            background: #e0e0e0;
                            transition: all 0.3s ease;
                            &.active {
                                background: linear-gradient(135deg, var(--nd-primary-300), var(--nd-primary-100));
                                transform: scale(1.2);
                                box-shadow: 0 2px 8px rgba(47, 156, 139, 0.35);
                            }
                        }
                    }
                    .intensity-text {
                        font-size: 12px;
                        color: var(--nd-text-2);
                        font-weight: 500;
                    }
                }
                .warm-suggestion {
                    background: linear-gradient(135deg, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.8));
                    border-radius: 16px;
                    padding: 12px;
                    margin-bottom: 12px;
                    max-height: 110px;
                    overflow-y: auto;
                    scrollbar-width: thin;
                    display: flex;
                    align-items: flex-start;
                    gap: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.6);
                    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
                    .suggestion-icon {
                        font-size: 20px;
                        flex-shrink: 0;
                        margin-top: 2px;
                    }
                    .suggestion-content {
                        text-align: left;
                        flex: 1;
                        .suggestion-title {
                            font-size: 14px;
                            font-weight: 600;
                            color: var(--nd-text-2);
                            margin-bottom: 6px;
                        }
                        .suggestion-text {
                            font-size: 13px;
                            color: var(--nd-text-3);
                            line-height: 1.5;
                        }
                    }
                }
                .healing-actions {
                    margin-bottom: 16px;
                    .actions-title {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 8px;
                        font-size: 14px;
                        font-weight: 600;
                        color: var(--nd-text-2);
                        margin-bottom: 16px;
                    }
                    .actions-list {
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                        .action-item {
                            background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.7));
                            border-radius: 12px;
                            padding: 12px;
                            display: flex;
                            align-items: center;
                            gap: 10px;
                            border: 1px solid rgba(255, 255, 255, 0.5);
                            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
                            text-align: left;
                            .action-icon {
                                font-size: 14px;
                                color: var(--nd-accent-500);
                                flex-shrink: 0;
                            }
                            .action-text {
                                font-size: 12px;
                                color: var(--nd-text-3);
                                line-height: 1.4;
                                flex: 1;
                            }
                        }
                    }
                }
                .risk-notice {
                    background: linear-gradient(135deg, var(--nd-warning-bg), var(--nd-accent-100));
                    border-radius: 16px;
                    padding: 16px;
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                    border: 1px solid rgba(255, 234, 167, 0.6);
                    box-shadow: 0 6px 20px rgba(255, 234, 167, 0.3);
                    .notice-icon {
                        font-size: 20px;
                        flex-shrink: 0;
                        margin-top: 2px;
                    }
                    .notice-content {
                        flex: 1;
                        .notice-title {
                            font-size: 14px;
                            font-weight: 600;
                            color: #d4840f;
                            margin-bottom: 6px;
                        }
                        .notice-text {
                            font-size: 13px;
                            color: #b8740c;
                            line-height: 1.5;
                        }
                    }
                }
            }
        }
    }
    .chat-main {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(255, 252, 250, 0.98) 100%);
        border-radius: 20px;
        box-shadow: 0 12px 40px rgba(47, 156, 139, 0.08), 0 4px 16px rgba(0, 0, 0, 0.04);
        border: 1px solid rgba(47, 156, 139, 0.1);
        backdrop-filter: blur(10px);
        display: flex;
        flex-direction: column;
        overflow: hidden;
        flex: 1;
        height: 100%;
        .chat-header {
            background: linear-gradient(135deg, var(--nd-primary-400) 0%, var(--nd-primary-500) 100%);
            color: white;
            padding: 20px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: relative;
            flex-shrink: 0;
            .header-left {
                display: flex;
                align-items: center;
                .chat-avatar {
                    width: 48px;
                    height: 48px;
                    background: rgba(255, 255, 255, 0.25);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 16px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    position: relative;
                    z-index: 1;
                }
                .chat-info {
                    h2 {
                        font-size: 20px;
                        font-weight: 700;
                        margin-bottom: 4px;
                    }
                    p {
                        font-size: 14px;
                    }
                }
            }
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px 24px;
            display: flex;
            flex-direction: column;
            gap: 14px;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, rgba(255, 252, 248, 0.05) 100%);
            min-height: 0;
            scrollbar-width: thin;
            scrollbar-color: rgba(47, 156, 139, 0.3) transparent;
            .message-item {
                display: flex;
                align-items: flex-start;
                gap: 12px;
                .message-avatar {
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 14px;
                    color: white;
                    flex-shrink: 0;
                }
                &.ai-message {
                    .message-avatar {
                        background: linear-gradient(135deg, var(--nd-primary-400), var(--nd-primary-500));
                        box-shadow: 0 4px 12px rgba(47, 156, 139, 0.3);
                    }
                }
                &.user-message {
                    .message-avatar {
                        background: linear-gradient(135deg, #6b7280, #4b5563);
                        box-shadow: 0 4px 12px rgba(107, 114, 128, 0.3);
                    }
                }
                .message-content {
                    max-width: 70%;
                    .message-bubble {
                        background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(255, 252, 248, 0.95) 100%);
                        border-radius: 16px;
                        padding: 12px 16px;
                        position: relative;
                        animation: fadeInUp 0.4s ease-out;
                        border: 1px solid rgba(47, 156, 139, 0.1);
                        box-shadow: 0 4px 16px rgba(47, 156, 139, 0.05);
                        .typing-indicator {
                            display: flex;
                            gap: 4px;
                            padding: 8px 0;
                            .typing-dot {
                                width: 8px;
                                height: 8px;
                                background: #ccc;
                                border-radius: 50%;
                                animation: typing 1.5s ease-in-out infinite;
                                &:nth-child(2) {
                                    animation-delay: 0.2s;
                                }
                                &:nth-child(3) {
                                    animation-delay: 0.4s;
                                }   
                            }
                        }
                        /* 错误消息样式 */
                        .error-message {
                            background: linear-gradient(135deg, #FEF2F2 0%, #FECACA 100%);
                            border: 1px solid #F87171;
                            border-radius: 12px;
                            padding: 12px 16px;
                            color: #991B1B;
                            font-weight: 500;
                            display: flex;
                            align-items: center;
                            gap: 8px;
                        }
                    }
                    .message-time {
                        font-size: 12px;
                        color: #999;
                        margin-top: 4px;
                    }
                }
            }
        }
        .crisis-card {
            margin-top: 8px;
            padding: 16px 18px;
            border-radius: 16px;
            background: linear-gradient(135deg, #fff1f2 0%, #ffe4e6 100%);
            border: 1px solid #fda4af;
            box-shadow: 0 6px 20px rgba(244, 63, 94, 0.12);
            flex-shrink: 0;
            .crisis-header {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 8px;
                .crisis-icon {
                    font-size: 18px;
                }
                .crisis-title {
                    font-size: 15px;
                    font-weight: 700;
                    color: #9f1239;
                    line-height: 1.4;
                }
            }
            .crisis-subtitle {
                font-size: 13px;
                color: #be123c;
                line-height: 1.6;
                margin-bottom: 10px;
            }
            .crisis-lines {
                margin: 0 0 10px;
                padding-left: 18px;
                li {
                    font-size: 13px;
                    color: #881337;
                    line-height: 1.8;
                }
            }
            .crisis-disclaimer {
                font-size: 12px;
                color: #a1665e;
                line-height: 1.5;
                margin-bottom: 6px;
            }
        }
        .disclaimer-bar {
            padding: 6px 24px;
            font-size: 12px;
            color: #9a3412;
            background: var(--nd-surface-soft);
            border-top: 1px solid var(--nd-primary-100);
            text-align: center;
            flex-shrink: 0;
        }
        .chat-input {
            border-top: 1px solid rgba(47, 156, 139, 0.1);
            padding: 20px 24px;
            display: flex;
            gap: 12px;
            align-items: flex-end;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.5) 0%, rgba(255, 252, 248, 0.7) 100%);
            backdrop-filter: blur(10px);
            flex-shrink: 0;
            .input-container {
                flex: 1;
            }
            .input-footer {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 12px;
                color: #78716c;
                font-weight: 500;
            }
            .send-btn {
                height: 60px;
                width: 60px;
                border-radius: 16px;
                background: linear-gradient(135deg, var(--nd-primary-400) 0%, var(--nd-primary-500) 100%) !important;
                border: none !important;
                box-shadow: 0 6px 20px rgba(47, 156, 139, 0.25);
                transition: all 0.3s ease;
            }

        }

    }
}
.agent-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    margin-bottom: 8px;
    background: #eef2ff;
    border: 1px solid #c7d2fe;
    border-radius: 8px;

    .agent-label {
        font-size: 13px;
        font-weight: 600;
        color: #4338ca;
        white-space: nowrap;
    }

    .agent-hint {
        font-size: 12px;
        color: #6366f1;
    }
}

.sources-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    padding: 10px 12px;
    margin-bottom: 10px;
    background: #f8fafc;
    border: 1px solid var(--nd-border);
    border-radius: 8px;

    .sources-label {
        font-size: 12px;
        color: #6b7280;
        white-space: nowrap;
    }

    .source-tag {
        cursor: pointer;

        &:hover {
            background: #e0e7ff;
        }
    }
}

/* 小屏：侧栏与对话区改为上下排列，取消各自的内部滚动，交给页面整体滚动 */
@media (max-width: 1024px) {
    .consultation-container {
        flex-direction: column;
        height: auto;
        min-height: 0;
        overflow: visible;

        .sidebar {
            width: 100%;
            height: auto;
            overflow: visible;
        }

        .chat-main {
            height: auto;
        }
    }
}
</style>
