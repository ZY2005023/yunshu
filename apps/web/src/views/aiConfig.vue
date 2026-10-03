<template>
    <div>
        <PageHead
            title="API 管理"
            subtitle="AI 服务的地址、模型与密钥 —— 保存后即时生效，无需重启服务"
        />

        <el-alert type="info" :closable="false" class="intro-alert">
            <p>
                API Key 保存后<b>不再回显</b>，只显示尾 4 位；输入框<b>留空表示保持现有 Key</b>，
                所以只想换个模型名时不需要重新粘贴密钥。
                「测试连接」会用<b>当前已生效</b>的配置发起一次真实的小请求。
            </p>
        </el-alert>

        <!-- ==================== 当前生效状态 ==================== -->
        <el-card class="status-card" v-loading="loading">
            <template #header>
                <div class="card-head">
                    <span>当前生效配置</span>
                    <el-tag :type="config.configured ? 'success' : 'danger'" size="small">
                        {{ config.configured ? '已配置' : '未配置（AI 功能不可用）' }}
                    </el-tag>
                </div>
            </template>

            <div class="status-grid">
                <div class="status-item">
                    <p class="status-label">API Key</p>
                    <p class="status-value mono">
                        {{ config.apiKeySet ? config.apiKeyMasked : '未设置' }}
                    </p>
                    <SourceBadge :source="config.sources && config.sources['ai.api_key']" />
                </div>
                <div class="status-item">
                    <p class="status-label">Base URL</p>
                    <p class="status-value mono">{{ config.baseUrl || '—' }}</p>
                    <SourceBadge :source="config.sources && config.sources['ai.base_url']" />
                </div>
                <div class="status-item">
                    <p class="status-label">模型</p>
                    <p class="status-value mono">{{ config.model || '—' }}</p>
                    <SourceBadge :source="config.sources && config.sources['ai.model']" />
                </div>
            </div>
        </el-card>

        <!-- ==================== 编辑配置 ==================== -->
        <el-card class="form-card">
            <template #header>
                <div class="card-head">
                    <span>修改配置</span>
                </div>
            </template>

            <el-form label-position="top" class="config-form">
                <el-form-item label="供应商预设">
                    <el-select
                        v-model="preset"
                        placeholder="选择后自动填入地址与模型名，可再手改"
                        style="width: 100%"
                        @change="applyPreset"
                    >
                        <el-option
                            v-for="p in PRESETS"
                            :key="p.label"
                            :label="p.label"
                            :value="p.label"
                        />
                    </el-select>
                </el-form-item>

                <el-form-item label="Base URL">
                    <el-input v-model="form.baseUrl" placeholder="https://api.deepseek.com" clearable />
                </el-form-item>

                <el-form-item label="模型名称">
                    <el-input v-model="form.model" placeholder="deepseek-chat" clearable />
                </el-form-item>

                <el-form-item label="API Key">
                    <el-input
                        v-model="form.apiKey"
                        type="password"
                        show-password
                        :placeholder="config.apiKeySet ? '已配置，留空保持现有 Key' : 'sk-...'"
                        autocomplete="new-password"
                    />
                </el-form-item>

                <div class="form-actions">
                    <el-button type="primary" :loading="saving" @click="save">
                        {{ saving ? '保存中…' : '保存配置' }}
                    </el-button>
                    <el-button :loading="testing" @click="runTest">
                        {{ testing ? '测试中…' : '测试连接' }}
                    </el-button>
                </div>
            </el-form>
        </el-card>

        <!-- ==================== 连通性测试结果 ==================== -->
        <el-alert
            v-if="testResult"
            :type="testResult.ok ? 'success' : 'error'"
            :closable="true"
            class="test-result"
            @close="testResult = null"
        >
            <template #title>
                <template v-if="testResult.ok">
                    连接正常 · {{ testResult.model }} · {{ testResult.latencyMs }}ms
                    <span v-if="testResult.reply"> · 模型回复：{{ testResult.reply }}</span>
                </template>
                <template v-else>连接失败（{{ testResult.latencyMs }}ms）：{{ testResult.error }}</template>
            </template>
        </el-alert>
    </div>
</template>

<script setup>
/**
 * 管理端 · API 管理（AI 服务配置）。
 *
 * 形态参考 one-api / new-api 的渠道管理页：
 *  · 当前生效配置一目了然（密钥只露尾 4 位 + 来源徽标：数据库 / 环境变量 / 默认）；
 *  · 供应商预设一键填入 base_url + 模型名，也可完全自定义（兼容 OpenAI 协议即可）；
 *  · 保存后**即时生效** —— 后续对话 / 日记分析 / 连通测试立即用新配置，不重启；
 *  · 「测试连接」发一个极小请求，失败时后端把 401 / 404 / 超时翻译成可读文案。
 */
import { onMounted, reactive, ref, h } from 'vue'
import { ElMessage } from 'element-plus'
import PageHead from '@/components/PageHead.vue'
import { getAiConfig, updateAiConfig, testAiConfig } from '@/api/admin'

/** 常见供应商预设。base_url 均兼容 OpenAI 协议；模型名给各家当前主力对话模型 */
const PRESETS = [
    { label: 'DeepSeek', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
    { label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
    { label: 'Moonshot（Kimi）', baseUrl: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
    { label: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
    { label: '自定义（兼容 OpenAI 协议）', baseUrl: '', model: '' }
]

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const preset = ref('')
const testResult = ref(null)

const config = reactive({
    baseUrl: '',
    model: '',
    apiKeyMasked: '',
    apiKeySet: false,
    configured: false,
    sources: {}
})

const form = reactive({
    baseUrl: '',
    model: '',
    apiKey: ''
})

/** 来源徽标：让管理员知道每个字段现在被谁控制（页面上改过 = 数据库） */
const SourceBadge = (props) => {
    const map = {
        database: { text: '数据库', type: 'success' },
        env: { text: '环境变量', type: 'info' },
        default: { text: '默认值', type: 'info' }
    }
    const item = map[props.source] || null
    if (!item) return null
    return h(
        'span',
        { class: `source-badge source-badge--${item.type}` },
        item.text
    )
}
SourceBadge.props = { source: { type: String, default: '' } }

const applyPreset = (label) => {
    const p = PRESETS.find((x) => x.label === label)
    if (!p) return
    if (p.baseUrl) form.baseUrl = p.baseUrl
    if (p.model) form.model = p.model
}

const load = async () => {
    loading.value = true
    try {
        const data = await getAiConfig()
        Object.assign(config, data || {})
        // 表单预填当前值；Key 一律留空（留空 = 保持现有值）
        form.baseUrl = config.baseUrl || ''
        form.model = config.model || ''
        form.apiKey = ''
    } finally {
        loading.value = false
    }
}

const save = async () => {
    saving.value = true
    try {
        const data = await updateAiConfig({
            baseUrl: form.baseUrl.trim(),
            model: form.model.trim(),
            // 留空 = 保持现有 Key；后端对空串就是"不修改"语义
            apiKey: form.apiKey.trim()
        })
        Object.assign(config, data || {})
        form.apiKey = ''
        ElMessage.success('已保存并即时生效')
        testResult.value = null
    } catch (e) {
        // 失败提示已由请求层统一给出
    } finally {
        saving.value = false
    }
}

const runTest = async () => {
    testing.value = true
    try {
        testResult.value = await testAiConfig()
    } catch (e) {
        testResult.value = null
    } finally {
        testing.value = false
    }
}

onMounted(load)
</script>

<style scoped>
.intro-alert {
    margin-bottom: 16px;
}
.status-card {
    margin-bottom: 16px;
}
.card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: 600;
}
.status-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 16px;
}
.status-label {
    margin: 0 0 4px;
    font-size: 12px;
    color: var(--nd-text-3);
}
.status-value {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 600;
    color: var(--nd-text-1);
    word-break: break-all;
}
.mono {
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.form-card {
    max-width: 640px;
}
.config-form :deep(.el-form-item__label) {
    font-weight: 600;
}
.form-actions {
    display: flex;
    gap: 12px;
}
.test-result {
    margin-top: 16px;
    max-width: 640px;
}
.source-badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 12px;
    line-height: 18px;
}
.source-badge--success {
    background: var(--nd-primary-100, #e6f4f1);
    color: var(--nd-primary-700, #1c6b63);
}
.source-badge--info {
    background: var(--nd-surface-soft, #f1f5f4);
    color: var(--nd-text-2, #5a6b67);
}
@media (max-width: 768px) {
    .status-grid {
        grid-template-columns: 1fr;
    }
}
</style>
