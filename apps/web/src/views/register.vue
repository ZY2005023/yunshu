<template>
    <div class="auth-form">
        <div class="form-head">
            <button class="back-home" type="button" @click="router.push('/')">
                <el-icon><Back /></el-icon>
                <span>返回首页</span>
            </button>
            <h2 class="form-title">创建账户</h2>
            <p class="form-sub">填写基本信息即可开始，昵称和手机号可以稍后再补</p>
        </div>

        <el-form
            ref="submitFormRef"
            label-position="top"
            size="large"
            :model="formData"
            :rules="rules"
            @submit.prevent
        >
            <p class="group-label">账号信息</p>

            <el-form-item label="用户名" prop="username">
                <el-input
                    v-model="formData.username"
                    :prefix-icon="User"
                    placeholder="3-50 位字母、数字或下划线"
                    clearable
                />
            </el-form-item>

            <el-form-item label="邮箱" prop="email">
                <el-input
                    v-model="formData.email"
                    :prefix-icon="Message"
                    placeholder="用于账号识别，不会公开显示"
                    clearable
                />
            </el-form-item>

            <div class="field-row">
                <el-form-item label="昵称（可选）" prop="nickname">
                    <el-input v-model="formData.nickname" placeholder="希望我们怎么称呼你" clearable />
                </el-form-item>
                <el-form-item label="手机号（可选）" prop="phone">
                    <el-input v-model="formData.phone" placeholder="选填" clearable />
                </el-form-item>
            </div>

            <p class="group-label">安全设置</p>

            <el-form-item label="密码" prop="password">
                <el-input
                    v-model="formData.password"
                    :prefix-icon="Lock"
                    type="password"
                    placeholder="至少 6 位，建议字母与数字组合"
                    show-password
                    autocomplete="new-password"
                />
                <!-- 强度提示：只在用户输入后出现，不占初始视觉重量 -->
                <div v-if="formData.password" class="strength">
                    <span
                        v-for="n in 3"
                        :key="n"
                        class="strength-bar"
                        :class="{ on: strength.score >= n, [`lv-${strength.score}`]: strength.score >= n }"
                    ></span>
                    <span class="strength-text" :class="`lv-${strength.score}`">{{ strength.label }}</span>
                </div>
            </el-form-item>

            <el-form-item label="确认密码" prop="confirmPassword">
                <el-input
                    v-model="formData.confirmPassword"
                    :prefix-icon="Lock"
                    type="password"
                    placeholder="请再次输入密码"
                    show-password
                    autocomplete="new-password"
                    @keyup.enter="submitForm(submitFormRef)"
                />
            </el-form-item>

            <el-form-item prop="agreed" class="agree-item">
                <el-checkbox v-model="formData.agreed">
                    我已阅读并同意
                    <a class="link" @click.prevent="showPolicy('用户协议')">《用户协议》</a>
                    与
                    <a class="link" @click.prevent="showPolicy('隐私政策')">《隐私政策》</a>
                </el-checkbox>
            </el-form-item>

            <el-button
                class="submit-btn"
                type="primary"
                size="large"
                :loading="loading"
                @click="submitForm(submitFormRef)"
            >
                {{ loading ? '注册中…' : '注册' }}
            </el-button>
        </el-form>

        <div class="form-foot">
            <p>已有账户？<router-link class="link link--strong" to="/auth/login">直接登录</router-link></p>
        </div>

        <PolicyDialog ref="policyRef" />
    </div>
</template>

<script setup>
/**
 * 注册页。
 *
 * 改版要点：
 *  - 字段按「账号信息 / 安全设置」分组，并明确标注可选项；
 *  - 密码加实时强度提示，减少「注册完就忘记/太弱被拒」的挫败感；
 *  - 协议改为强制勾选（心理类产品涉及敏感数据，属于必要告知）；
 *  - 前端补齐用户名、邮箱、手机号格式校验，避免提交后才被后端打回；
 *  - 注册成功后把用户名写入「记住用户名」，登录页会自动预填。
 */
import { ref, reactive, computed } from 'vue'
import { User, Lock, Message } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { register } from '@/api/frontend'
import PolicyDialog from '@/components/PolicyDialog.vue'

const router = useRouter()
const submitFormRef = ref(null)
const loading = ref(false)
const policyRef = ref(null)
const showPolicy = (name) => policyRef.value?.show(name)

const formData = reactive({
    username: '',
    email: '',
    nickname: '',
    phone: '',
    password: '',
    confirmPassword: '',
    agreed: false,
    gender: 0, // 性别
    userType: 1 // 1 为普通用户；后端也会强制，这里只是保持结构一致
})

/** 密码强度：长度 + 字符种类，三档足矣，不做复杂评分免得误导 */
const strength = computed(() => {
    const v = formData.password || ''
    if (!v) return { score: 0, label: '' }
    let kinds = 0
    if (/[a-z]/.test(v)) kinds += 1
    if (/[A-Z]/.test(v)) kinds += 1
    if (/\d/.test(v)) kinds += 1
    if (/[^a-zA-Z0-9]/.test(v)) kinds += 1
    if (v.length < 6) return { score: 1, label: '过短' }
    if (v.length >= 10 && kinds >= 3) return { score: 3, label: '强' }
    if (v.length >= 8 && kinds >= 2) return { score: 2, label: '中' }
    return { score: 1, label: '弱' }
})

const validateConfirm = (_rule, value, callback) => {
    if (!value) return callback(new Error('请再次输入密码'))
    if (value !== formData.password) return callback(new Error('两次输入的密码不一致'))
    return callback()
}

const rules = reactive({
    username: [
        { required: true, message: '请输入用户名', trigger: 'blur' },
        {
            pattern: /^[a-zA-Z0-9_]{3,50}$/,
            message: '3-50 位字母、数字或下划线',
            trigger: 'blur'
        }
    ],
    email: [
        { required: true, message: '请输入邮箱', trigger: 'blur' },
        { type: 'email', message: '邮箱格式不正确', trigger: 'blur' }
    ],
    phone: [
        { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }
    ],
    password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, message: '密码至少 6 位', trigger: 'blur' }
    ],
    confirmPassword: [{ validator: validateConfirm, trigger: 'blur' }],
    agreed: [
        {
            validator: (_r, v, cb) => (v ? cb() : cb(new Error('请先阅读并同意用户协议与隐私政策'))),
            trigger: 'change'
        }
    ]
})

const submitForm = (formEl) => {
    if (!formEl || loading.value) return
    formEl.validate((valid) => {
        if (!valid) return
        loading.value = true
        // 手机号留空时传 null（后端 @Pattern 会校验空字符串导致误报"格式错误"）
        const payload = { ...formData, phone: formData.phone ? formData.phone : null }
        delete payload.agreed

        register(payload)
            .then((res) => {
                // 成功: 拦截器已剥一层, res 直接是用户详情对象(含 id)
                if (res && res.id) {
                    // 预填登录页的用户名，省一步输入
                    localStorage.setItem('nd_remember_username', formData.username)
                    ElMessage.success('注册成功，请登录')
                    router.push('/auth/login')
                } else if (res && res.data && res.data.code) {
                    ElMessage.error(res.data.data || res.data.msg || '注册失败')
                } else {
                    ElMessage.error('注册失败，请稍后重试')
                }
            })
            .catch(() => {
                ElMessage.error('网络异常，请稍后重试')
            })
            .finally(() => {
                loading.value = false
            })
    })
}
</script>

<style scoped lang="scss">
.auth-form {
    width: 100%;
    max-width: 420px;
    animation: nd-fade-up 0.4s var(--nd-ease) both;
}

.form-head {
    margin-bottom: 22px;

    .back-home {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 22px;
        padding: 0;
        border: 0;
        background: none;
        cursor: pointer;
        font-size: 13px;
        color: var(--nd-text-3);
        transition: color var(--nd-duration) var(--nd-ease);

        &:hover {
            color: var(--nd-primary-500);
        }
    }

    .form-title {
        font-size: 30px;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .form-sub {
        margin-top: 8px;
        font-size: 14px;
        color: var(--nd-text-3);
    }
}

.group-label {
    margin: 4px 0 14px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--nd-text-4);
    text-transform: uppercase;

    &:not(:first-child) {
        margin-top: 10px;
        padding-top: 18px;
        border-top: 1px dashed var(--nd-border);
    }
}

.field-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 14px;
}

/* 密码强度条 */
.strength {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
    line-height: 1;

    .strength-bar {
        width: 34px;
        height: 4px;
        border-radius: var(--nd-radius-full);
        background: var(--nd-border);
        transition: background var(--nd-duration) var(--nd-ease);

        &.lv-1 {
            background: var(--nd-danger);
        }
        &.lv-2 {
            background: var(--nd-warning);
        }
        &.lv-3 {
            background: var(--nd-success);
        }
    }

    .strength-text {
        margin-left: 4px;
        font-size: 12px;

        &.lv-1 {
            color: var(--nd-danger);
        }
        &.lv-2 {
            color: var(--nd-warning);
        }
        &.lv-3 {
            color: var(--nd-success);
        }
    }
}

.agree-item {
    margin-top: 6px;
    margin-bottom: 18px;
}

.submit-btn {
    width: 100%;
    height: 46px;
    font-size: 15px;
    letter-spacing: 0.05em;
}

.form-foot {
    margin-top: 20px;
    text-align: center;
    font-size: 14px;
    color: var(--nd-text-3);
}

.link {
    color: var(--nd-primary-500);
    cursor: pointer;
    transition: color var(--nd-duration) var(--nd-ease);

    &:hover {
        color: var(--nd-primary-600);
        text-decoration: underline;
    }
}

.link--strong {
    font-weight: 600;
}

:deep(.el-form-item__label) {
    font-weight: 500;
    color: var(--nd-text-2);
    padding-bottom: 4px;
}

:deep(.el-form-item) {
    margin-bottom: 18px;
}

:deep(.agree-item .el-checkbox__label) {
    font-size: 13px;
    color: var(--nd-text-3);
}

@media (max-width: 860px) {
    .field-row {
        grid-template-columns: 1fr;
        gap: 0;
    }
}
</style>
