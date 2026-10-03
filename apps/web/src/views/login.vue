<template>
    <div class="auth-form">
        <div class="form-head">
            <button class="back-home" type="button" @click="router.push('/')">
                <el-icon><Back /></el-icon>
                <span>返回首页</span>
            </button>
            <h2 class="form-title">欢迎回来</h2>
            <p class="form-sub">继续记录你的心情，我们一直在这</p>
        </div>

        <el-form
            ref="ruleFormRef"
            :model="formData"
            :rules="rules"
            label-position="top"
            size="large"
            @submit.prevent
        >
            <el-form-item label="用户名或邮箱" prop="username">
                <el-input
                    v-model="formData.username"
                    :prefix-icon="User"
                    placeholder="请输入用户名或邮箱"
                    autocomplete="username"
                    clearable
                    @keyup.enter="submitForm(ruleFormRef)"
                />
            </el-form-item>

            <el-form-item label="密码" prop="password">
                <el-input
                    v-model="formData.password"
                    :prefix-icon="Lock"
                    type="password"
                    placeholder="请输入密码"
                    autocomplete="current-password"
                    show-password
                    @keyup.enter="submitForm(ruleFormRef)"
                />
            </el-form-item>

            <div class="form-row">
                <el-checkbox v-model="rememberMe">记住用户名</el-checkbox>
                <a class="link" @click="handleForgot">忘记密码？</a>
            </div>

            <el-button
                class="submit-btn"
                type="primary"
                size="large"
                :loading="loading"
                @click="submitForm(ruleFormRef)"
            >
                {{ loading ? '登录中…' : '登录' }}
            </el-button>
        </el-form>

        <div class="form-foot">
            <p>还没有账户？<router-link class="link link--strong" to="/auth/register">立即注册</router-link></p>
            <p class="agreement">
                登录即代表你已阅读并同意
                <a class="link" @click="showPolicy('用户协议')">《用户协议》</a>
                与
                <a class="link" @click="showPolicy('隐私政策')">《隐私政策》</a>
            </p>
        </div>

        <PolicyDialog ref="policyRef" />
    </div>
</template>

<script setup>
/**
 * 登录页。
 *
 * 改版要点：
 *  - 输入框补图标与自动填充属性（浏览器能正确识别账号/密码字段）；
 *  - 增加「记住用户名」与「忘记密码」入口（原先完全没有，用户会卡住）；
 *  - 补充协议提示与加载态，避免重复点击；
 *  - 修一个历史隐患：原来判断管理员用 `userType === 2` 严格比较，
 *    而 localStorage 里的值来源不定，若存成字符串 "2" 就会误判成普通用户。
 *    统一改为 Number() 转换后再比较（与路由守卫保持一致）。
 */
import { ref, reactive, onMounted } from 'vue'
import { User, Lock } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter, useRoute } from 'vue-router'
import { login } from '@/api/admin'
import PolicyDialog from '@/components/PolicyDialog.vue'

const REMEMBER_KEY = 'nd_remember_username'

const router = useRouter()
const route = useRoute()

const ruleFormRef = ref()
const loading = ref(false)
const rememberMe = ref(false)

const formData = reactive({
    username: '',
    password: ''
})

const rules = reactive({
    username: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }],
    password: [
        { required: true, message: '请输入密码', trigger: 'blur' },
        { min: 6, message: '密码至少 6 位', trigger: 'blur' }
    ]
})

const submitForm = (formEl) => {
    if (!formEl) return
    formEl.validate((valid) => {
        if (!valid || loading.value) return
        loading.value = true
        login(formData)
            .then((data) => {
                // 成功时拦截器已剥层：直接拿到 { token, refreshToken, roleType, userInfo }
                if (!data || !data.token) {
                    ElMessage.error('登录失败，请检查用户名和密码')
                    return
                }
                localStorage.setItem('token', data.token)
                if (data.refreshToken) {
                    localStorage.setItem('refreshToken', data.refreshToken)
                }
                localStorage.setItem('userInfo', JSON.stringify(data.userInfo))

                // 记住用户名：只存用户名，绝不存密码
                if (rememberMe.value) {
                    localStorage.setItem(REMEMBER_KEY, formData.username)
                } else {
                    localStorage.removeItem(REMEMBER_KEY)
                }

                ElMessage.success('登录成功，欢迎回来')
                // 登录前想去的页面(如从"开始倾诉"被引导而来)优先
                const redirect = route.query.redirect
                if (redirect) {
                    router.push(redirect)
                } else if (Number(data.userInfo.userType) === 2) {
                    router.push('/back/dashboard')
                } else {
                    router.push('/consultation')
                }
            })
            .catch(() => {
                // 失败提示已由请求拦截器统一给出，这里不再重复提示
            })
            .finally(() => {
                loading.value = false
            })
    })
}

const handleForgot = () => {
    ElMessageBox.alert(
        '为保护隐私，密码不支持在线自助找回，系统也不会向邮箱发送重置链接。' +
            '如果你还处于登录状态，可在「个人中心 → 修改密码」自助修改；' +
            '若已无法登录，请联系学校心理健康教育中心的老师协助重置。',
        '忘记密码',
        { confirmButtonText: '我知道了' }
    )
}

const policyRef = ref(null)
const showPolicy = (name) => policyRef.value?.show(name)

onMounted(() => {
    const saved = localStorage.getItem(REMEMBER_KEY)
    if (saved) {
        formData.username = saved
        rememberMe.value = true
    }
})
</script>

<style scoped lang="scss">
.auth-form {
    width: 100%;
    max-width: 400px;
    animation: nd-fade-up 0.4s var(--nd-ease) both;
}

.form-head {
    margin-bottom: 28px;

    .back-home {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 26px;
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

.form-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 4px 0 22px;
}

.submit-btn {
    width: 100%;
    height: 46px;
    font-size: 15px;
    letter-spacing: 0.05em;
}

.form-foot {
    margin-top: 24px;
    text-align: center;
    font-size: 14px;
    color: var(--nd-text-3);

    p + p {
        margin-top: 14px;
    }

    .agreement {
        font-size: 12px;
        line-height: 1.7;
        color: var(--nd-text-4);
        padding: 0 6px;
    }
}

/* 链接样式统一。用 <a> 而非 router-link 的场景（弹窗、占位）不会有下划线 */
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
</style>
