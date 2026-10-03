<template>
    <div class="nd-page">
        <div class="nd-container profile">
            <div class="profile-head nd-card">
                <UserAvatar
                    :name="displayName"
                    :seed="form.id || form.username"
                    :size="64"
                />
                <div class="profile-head__text">
                    <h1 class="profile-head__name">{{ displayName }}</h1>
                    <p class="profile-head__mail">{{ form.email || '未填写邮箱' }}</p>
                    <div class="profile-head__tags">
                        <span class="nd-badge">{{ roleText }}</span>
                        <span v-if="form.createdAt" class="nd-muted">
                            {{ String(form.createdAt).slice(0, 10) }} 加入
                        </span>
                    </div>
                </div>
            </div>

            <div class="profile-grid">
                <section class="nd-card">
                    <div class="card-head">
                        <h2 class="card-head__title">基本资料</h2>
                        <p class="card-head__sub">这些信息只有你和管理后台能看到</p>
                    </div>

                    <el-form
                        ref="profileFormRef"
                        :model="profileForm"
                        :rules="profileRules"
                        label-position="top"
                    >
                        <el-form-item label="用户名">
                            <el-input :model-value="form.username" disabled />
                            <p class="field-hint">用户名用于登录，不可修改</p>
                        </el-form-item>

                        <el-form-item label="昵称" prop="nickname">
                            <el-input v-model="profileForm.nickname" maxlength="50" clearable />
                        </el-form-item>

                        <el-form-item label="手机号" prop="phone">
                            <el-input v-model="profileForm.phone" maxlength="11" clearable />
                            <p class="field-hint">选填。留空表示保持原值不变</p>
                        </el-form-item>

                        <div class="field-row">
                            <el-form-item label="性别" prop="gender">
                                <el-select v-model="profileForm.gender" placeholder="未填写" clearable>
                                    <el-option label="男" :value="1" />
                                    <el-option label="女" :value="2" />
                                </el-select>
                            </el-form-item>

                            <el-form-item label="生日" prop="birthday">
                                <el-date-picker
                                    v-model="profileForm.birthday"
                                    type="date"
                                    placeholder="选择日期"
                                    value-format="YYYY-MM-DD"
                                    :disabled-date="disableFuture"
                                />
                            </el-form-item>
                        </div>

                        <el-button type="primary" :loading="savingProfile" @click="saveProfile">
                            {{ savingProfile ? '保存中…' : '保存资料' }}
                        </el-button>
                    </el-form>
                </section>

                <section class="nd-card">
                    <div class="card-head">
                        <h2 class="card-head__title">修改密码</h2>
                        <p class="card-head__sub">
                            为了你的隐私安全，改完密码后<b>所有设备都会退出登录</b>，需要重新登录
                        </p>
                    </div>

                    <el-form
                        ref="pwdFormRef"
                        :model="pwdForm"
                        :rules="pwdRules"
                        label-position="top"
                    >
                        <el-form-item label="当前密码" prop="oldPassword">
                            <el-input
                                v-model="pwdForm.oldPassword"
                                type="password"
                                show-password
                                autocomplete="current-password"
                            />
                        </el-form-item>

                        <el-form-item label="新密码" prop="newPassword">
                            <el-input
                                v-model="pwdForm.newPassword"
                                type="password"
                                show-password
                                autocomplete="new-password"
                            />
                            <div class="strength">
                                <span
                                    v-for="i in 3"
                                    :key="i"
                                    class="strength__bar"
                                    :class="{ 'is-on': strength >= i, [`lv${strength}`]: strength >= i }"
                                />
                                <span class="strength__text">{{ strengthText }}</span>
                            </div>
                        </el-form-item>

                        <el-form-item label="确认新密码" prop="confirmPassword">
                            <el-input
                                v-model="pwdForm.confirmPassword"
                                type="password"
                                show-password
                                autocomplete="new-password"
                            />
                        </el-form-item>

                        <el-button type="primary" :loading="savingPwd" @click="savePassword">
                            {{ savingPwd ? '提交中…' : '修改密码' }}
                        </el-button>
                    </el-form>

                    <el-divider />

                    <div class="tip-block">
                        <p class="tip-block__title">忘记密码怎么办</p>
                        <p class="nd-muted">
                            本系统不提供在线自助找回（也不会向邮箱发送重置链接）。
                            若已无法登录，请联系学校心理健康教育中心的老师协助重置。
                        </p>
                    </div>
                </section>
            </div>
        </div>
    </div>
</template>

<script setup>
/**
 * 个人中心。
 *
 * 补的是一个**断链**：后端 `/api/user/password` 一直可用，
 * `api/admin.js::changePassword` 也封装好了，但**全项目没有任何地方调用它** ——
 * 用户根本找不到改密码的入口，而登录页的「忘记密码」还指着这个不存在的页面。
 *
 * 两个必须处理对的细节：
 *  1. 改密后后端会吊销**全部令牌**，所以要主动清登录态并跳登录页。
 *     否则用户会停在页面上，之后每个请求都 401，体验很怪。
 *  2. 保存资料后要写进 user store —— 否则导航栏还显示旧昵称（布局不会因
 *     子路由切换而重新挂载）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePassword, getCurrentUser, updateProfile } from '@/api/admin'
import { useUserStore } from '@/stores/user'
import UserAvatar from '@/components/UserAvatar.vue'

const router = useRouter()
const userStore = useUserStore()

const form = ref({})
const profileFormRef = ref(null)
const pwdFormRef = ref(null)
const savingProfile = ref(false)
const savingPwd = ref(false)

const profileForm = reactive({
    nickname: '',
    phone: '',
    gender: null,
    birthday: ''
})

const pwdForm = reactive({
    oldPassword: '',
    newPassword: '',
    confirmPassword: ''
})

const displayName = computed(
    () => form.value.nickname || form.value.displayName || form.value.username || '未登录'
)
const roleText = computed(() => (form.value.userType === 2 ? '管理员' : '普通用户'))

const strength = computed(() => {
    const p = pwdForm.newPassword || ''
    if (p.length < 6) return 0
    let score = 1
    if (/[a-zA-Z]/.test(p) && /\d/.test(p)) score = 2
    if (p.length >= 10 && /[^a-zA-Z0-9]/.test(p)) score = 3
    return score
})
const strengthText = computed(() => ['', '偏弱', '一般', '较强'][strength.value] || '')

const disableFuture = (d) => d.getTime() > Date.now()

const profileRules = {
    nickname: [{ max: 50, message: '昵称不超过 50 个字', trigger: 'blur' }],
    phone: [
        {
            // 后端是 ^1[3-9]\d{9}$，前端先拦一道，避免提交后才被打回
            validator: (_r, v, cb) =>
                !v || /^1[3-9]\d{9}$/.test(v) ? cb() : cb(new Error('请输入 11 位手机号')),
            trigger: 'blur'
        }
    ]
}

const pwdRules = {
    oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
    newPassword: [
        { required: true, message: '请输入新密码', trigger: 'blur' },
        { min: 6, max: 64, message: '密码需 6-64 位', trigger: 'blur' }
    ],
    confirmPassword: [
        { required: true, message: '请再次输入新密码', trigger: 'blur' },
        {
            validator: (_r, v, cb) =>
                v === pwdForm.newPassword ? cb() : cb(new Error('两次输入的密码不一致')),
            trigger: 'blur'
        }
    ]
}

const load = async () => {
    const data = await getCurrentUser()
    form.value = data || {}
    profileForm.nickname = form.value.nickname || ''
    profileForm.phone = form.value.phone || ''
    profileForm.gender = form.value.gender ?? null
    profileForm.birthday = form.value.birthday || ''
}

const saveProfile = () => {
    profileFormRef.value?.validate(async (valid) => {
        if (!valid || savingProfile.value) return
        savingProfile.value = true

        // 只提交真正填了值的字段：后端对 None 是「跳过」语义，
        // 传空字符串反而会撞上手机号格式校验。
        const payload = {}
        if (profileForm.nickname.trim()) payload.nickname = profileForm.nickname.trim()
        if (profileForm.phone.trim()) payload.phone = profileForm.phone.trim()
        if (profileForm.gender) payload.gender = profileForm.gender
        if (profileForm.birthday) payload.birthday = profileForm.birthday

        try {
            const updated = await updateProfile(payload)
            form.value = updated || form.value
            // 同步 store —— 导航栏的昵称要立刻变
            userStore.setUserInfo(updated)
            ElMessage.success('资料已保存')
        } catch (e) {
            // 请求层已统一提示
        } finally {
            savingProfile.value = false
        }
    })
}

const savePassword = () => {
    pwdFormRef.value?.validate(async (valid) => {
        if (!valid || savingPwd.value) return
        savingPwd.value = true
        try {
            await changePassword({
                oldPassword: pwdForm.oldPassword,
                newPassword: pwdForm.newPassword,
                confirmPassword: pwdForm.confirmPassword
            })
            ElMessage.success('密码已修改，请用新密码重新登录')
            // 后端已吊销全部令牌（含刷新令牌），这里必须主动清登录态：
            // 留着旧 token 只会让后续每个请求都 401。
            localStorage.removeItem('token')
            localStorage.removeItem('refreshToken')
            userStore.clear()
            router.push('/auth/login')
        } catch (e) {
            // 请求层已统一提示（原密码错误等）
        } finally {
            savingPwd.value = false
        }
    })
}

onMounted(load)
</script>

<style scoped lang="scss">
.profile {
    padding-top: 24px;
    padding-bottom: 60px;
}

.profile-head {
    display: flex;
    align-items: center;
    gap: 18px;
    margin-bottom: var(--nd-gap-lg);

    &__name {
        margin: 0 0 4px;
        font-size: 22px;
        font-weight: 600;
        color: var(--nd-text-1);
    }

    &__mail {
        margin: 0 0 8px;
        font-size: 13.5px;
        color: var(--nd-text-3);
    }

    &__tags {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 13px;
    }
}

.profile-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: var(--nd-gap-lg);
    align-items: start;
}

/**
 * 卡片内的表头：左对齐、字号小。
 * 不能用 .nd-section-head —— 那是首页那种居中大标题（30px/text-align:center），
 * 放进卡片里会变成居中的粗大字，明显不对。
 */
.card-head {
    margin-bottom: 18px;

    &__title {
        margin: 0;
        font-size: 17px;
        font-weight: 600;
        color: var(--nd-text-1);
    }

    &__sub {
        margin: 5px 0 0;
        font-size: 12.5px;
        line-height: 1.6;
        color: var(--nd-text-3);
    }
}

.field-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
}

.field-hint {
    margin: 4px 0 0;
    font-size: 12px;
    line-height: 1.5;
    color: var(--nd-text-4);
}

.card-head__sub b {
    color: var(--nd-text-1);
}

.strength {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-top: 7px;

    &__bar {
        width: 42px;
        height: 4px;
        border-radius: var(--nd-radius-full);
        background: var(--nd-border);

        &.is-on.lv1 {
            background: var(--nd-danger);
        }

        &.is-on.lv2 {
            background: var(--nd-warning);
        }

        &.is-on.lv3 {
            background: var(--nd-primary-500);
        }
    }

    &__text {
        margin-left: 4px;
        font-size: 12px;
        color: var(--nd-text-3);
    }
}

.tip-block {
    &__title {
        margin: 0 0 6px;
        font-size: 13.5px;
        font-weight: 600;
        color: var(--nd-text-1);
    }

    p:last-child {
        margin: 0;
        font-size: 13px;
        line-height: 1.7;
    }
}
</style>
