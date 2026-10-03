import service from '@/utils/request'

export function login(data) {
    return service.post('/user/login', data)
}

/** 拉取当前登录用户的最新信息（用于校验 token 是否还有效） */
export function getCurrentUser() {
    return service.get('/user/current')
}

/** 修改密码（成功后所有旧令牌失效，需要重新登录） */
export function changePassword(data) {
    return service.post('/user/password', data)
}

/**
 * 更新个人资料。
 * 只能改 昵称/头像/手机/性别/生日 —— 用户名、邮箱、角色、状态后端一律不接受
 * （白名单在 services/user.py 的 PROFILE_EDITABLE）。
 */
export function updateProfile(data) {
    return service.put('/user/profile', data)
}

// ===== 用户管理（管理端）=====
export function getUserPage(params) {
    return service.get('/user/admin/page', { params })
}

/** 0 = 禁用，1 = 正常。禁用/解禁都会让对方的旧令牌立即失效。 */
export function setUserStatus(id, status) {
    return service.put(`/user/admin/${id}/status`, { status })
}

/** 重置他人密码，不需要原密码 —— 这是「忘记密码」缺的那个出口。 */
export function resetUserPassword(id, newPassword) {
    return service.post(`/user/admin/${id}/password`, { newPassword })
}

export function categoryTree() {
    return service.get('/knowledge/category/tree')
}

export function articlePage(params) {
    return service.get('/knowledge/article/page', { params })
}

export function uploadFile(file, businessInfo) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('businessType', 'ARTICLE')
    formData.append('businessId', businessInfo.businessId)
    formData.append('businessField', 'cover')

    return service.post('/file/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data'
        }
    })
}

export function createArticle(data) {
    return service.post('/knowledge/article', data)
}

/**
 * 文档导入（知识库用）：上传 txt/md/docx/pdf → 解析出标题与正文（HTML）。
 * 只解析、不落库 —— 返回内容预填到编辑器，管理员校对后仍走 createArticle 保存。
 */
export function importDocument(file) {
    const formData = new FormData()
    formData.append('file', file)
    return service.post('/knowledge/admin/import-document', formData, {
        headers: {
            'Content-Type': 'multipart/form-data'
        },
        timeout: 60000
    })
}

export function getArticleDetail(id) {
    return service.get(`/knowledge/article/${id}`)
}

export function updateArticle(id, data) {
    return service.put(`/knowledge/article/${id}`, data)
}

export function changeArticleStatus(id, data) {
    return service.put(`/knowledge/article/${id}/status`, data)
}

export function deleteArticle(id) {
    return service.delete(`/knowledge/article/${id}`)
}

/**
 * 管理端：全站咨询会话列表。
 * 注意：用户端的 /psychological-chat/sessions 现在只返回自己的会话，
 * 后台必须走 /admin/sessions（需 ADMIN 角色）。
 */
export function getConsultationPage(params) {
    return service.get('/psychological-chat/admin/sessions', { params })
}

export function getSessionDetail(sessionId) {
    return service.get(`/psychological-chat/sessions/${sessionId}/messages`)
}

export function getEmotionalPage(params) {
    return service.get('/emotion-diary/admin/page', { params })
}

export function deleteEmotional(id) {
    return service.delete(`/emotion-diary/admin/${id}`)
}

export function getAnalyticsOverview() {
    return service.get(`/data-analytics/overview`)
}

// ===== 危机预警工单（管理端）=====
export function getCrisisPage(params) {
    return service.get('/admin/crisis/page', { params })
}

export function getCrisisPendingCount() {
    return service.get('/admin/crisis/pending/count')
}

export function handleCrisisEvent(id, data) {
    return service.post(`/admin/crisis/${id}/handle`, data)
}

/**
 * 工单「处置上下文」—— 一屏返回处置所需的一切：
 * 用户画像 / 历史工单 / 量表 / 日记趋势 / 触发原文（完整）/ 跟进记录 / 处置清单。
 *
 * 为什么必须新增这个接口：原来详情弹窗只有「用户ID: 52」和一句 120 字片段，
 * 管理员根本无从判断这是真风险还是误报。
 */
export function getCrisisContext(id) {
    return service.get(`/admin/crisis/${id}/context`)
}

export function getCrisisFollowUps(id) {
    return service.get(`/admin/crisis/${id}/follow-ups`)
}

/** 追加一条跟进记录（对已关闭工单会将其拉回「处理中」） */
export function addCrisisFollowUp(id, content) {
    return service.post(`/admin/crisis/${id}/follow-ups`, { content })
}

/** 固定求助资源（热线等），管理端处置时可一键参考 */
export function getCrisisResources() {
    return service.get('/admin/crisis/resources')
}

// ===== 量表记录（管理端）=====
export function getScaleRecordPage(params) {
    return service.get('/scale/admin/page', { params })
}

// ===== API 管理（AI 服务配置，管理端）=====
/** 当前生效配置。apiKey 只回掩码（尾 4 位），sources 标明每个字段来自数据库还是环境变量 */
export function getAiConfig() {
    return service.get('/admin/ai-config')
}

/**
 * 保存 AI 服务配置，保存后即时生效（对话/日记分析/连通测试都会立即用新值）。
 * 部分更新：apiKey 留空 = 保持现有 Key（换模型名时不必重新粘贴密钥）。
 */
export function updateAiConfig(data) {
    return service.put('/admin/ai-config', data)
}

/** 用当前生效配置发一个极小请求验证连通性；失败也是 code=200 + ok=false */
export function testAiConfig() {
    return service.post('/admin/ai-config/test')
}

/**
 * 重建知识库检索索引（RAG）。
 * 正常不用手动跑 —— 文章的增删改会自动重建。这里用于首次启用或批量导入后修复。
 */
export function reindexKnowledge() {
    return service.post('/knowledge/admin/reindex')
}

export function logout(refreshToken) {
    return service.post('/user/logout', { refreshToken: refreshToken || '' })
}
