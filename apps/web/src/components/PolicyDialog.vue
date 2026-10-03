<template>
    <!--
        append-to-body 必须开着。登录/注册页的 .auth-form 上有
        `animation: nd-fade-up ... both` —— 带 transform 的动画元素会成为
        `position: fixed` 的**包含块**，弹窗会被限制在表单列里、右侧被裁掉。
        挂到 body 才能正确相对视口居中。（这个坑只有真浏览器能看出来。）
    -->
    <el-dialog
        v-model="visible"
        :title="title"
        width="640px"
        top="6vh"
        append-to-body
        class="policy-dialog"
    >
        <div class="policy-body">
            <p class="policy-lead">
                云舒是一个心理健康自助与辅助工具。它不是医疗机构，不提供医学诊断，
                也不能替代专业心理咨询或紧急救援。
            </p>

            <section>
                <h4>一、我们收集什么</h4>
                <ul>
                    <li><b>账号信息</b>：用户名、邮箱、可选填的昵称/手机号/性别/生日。</li>
                    <li><b>你主动写下的内容</b>：与 AI 的对话、情绪日记、心理量表作答。</li>
                    <li><b>系统记录</b>：登录时间等运行日志。</li>
                </ul>
            </section>

            <section>
                <h4>二、用来做什么</h4>
                <ul>
                    <li>生成 AI 回复、情绪分析与量表结果反馈，供你自己查看。</li>
                    <li>在你的记录中出现明显风险信号时，形成记录以便提供帮助（见第五条）。</li>
                </ul>
                <p class="policy-note">不用于广告、营销，也不会出售或提供给校外第三方用于商业目的。</p>
            </section>

            <section>
                <h4>三、谁会看到</h4>
                <ul>
                    <li><b>你本人</b>：可以查看自己的全部记录。</li>
                    <li><b>学校心理健康教育中心的管理员（心理老师）</b>：可以通过管理后台查看对话记录、
                        情绪日记与量表结果，用于提供心理支持。</li>
                </ul>
                <p class="policy-strong">
                    请注意：你的记录<b>不是只有你一个人能看到</b>。请据此决定写什么。
                </p>
            </section>

            <section>
                <h4>四、内容会被发送给外部 AI 服务</h4>
                <p>
                    为了生成回复和情绪分析，你的对话内容与日记正文会<b>发送给第三方 AI 服务</b>
                    进行处理。除此之外不会用于其他用途。
                </p>
            </section>

            <section>
                <h4>五、风险情形的例外</h4>
                <p>
                    如果对话或日记中出现自伤、自杀等风险信号，系统会<b>生成一条风险记录供心理老师查看</b>，
                    以便及时提供帮助。这是本系统唯一会主动提请他人关注的情形。
                </p>
                <p class="policy-strong">
                    但请务必理解：<b>这不是紧急救援通道</b>，不保证即时响应。
                    如果你或他人正处于危险中，请立即拨打 <b>120 / 110</b>，
                    或全国心理援助热线 <b>12356</b>。
                </p>
            </section>

            <section>
                <h4>六、存储与你的权利</h4>
                <ul>
                    <li>内容存放在<b>学校自建的服务器</b>上，访问受账号权限控制，未做额外加密处理。</li>
                    <li>目前<b>没有提供自助导出或自助注销</b>功能。如需导出、更正或删除你的数据，
                        请联系学校心理健康教育中心的管理员。</li>
                </ul>
            </section>

            <section>
                <h4>七、如果你是未成年人</h4>
                <p>
                    请在监护人知情的前提下使用。若你未满 14 周岁，建议由监护人或老师陪同了解本说明后再使用。
                </p>
            </section>

            <section>
                <h4>八、联系我们</h4>
                <p>
                    对本说明或你的数据有任何疑问，请联系<b>学校心理健康教育中心</b>。
                </p>
            </section>

            <p class="policy-foot">继续使用本系统，即表示你已阅读并理解以上说明。</p>
        </div>

        <template #footer>
            <el-button type="primary" @click="visible = false">我已阅读并理解</el-button>
        </template>
    </el-dialog>
</template>

<script setup>
/**
 * 用户协议 / 隐私说明弹窗。
 *
 * 为什么要单独做成组件：原来登录页和注册页各自写了一段 `ElMessageBox.alert`，
 * 只有三句话，把「内容加密存储」「不会向第三方披露」这类**做不到的承诺**写进去过。
 *
 * 本组件的写作原则：**每一句都要能对着代码验证**。
 *   · 不说「加密」——后端确实没有任何内容加密（字段是明文 Text）。
 *   · 不说「仅你本人可见」——管理端「情绪日志」「咨询记录」页能读到全部用户内容。
 *   · 主动写明「内容会发送给第三方 AI 服务」——对话与日记确实会调 DeepSeek。
 *   · 不承诺即时救援——危机通知依赖 webhook 配置，且不是急救通道。
 *
 * ⚠️ 这里是**技术事实陈述**，不是法律意见。正式上线前应由校方/法务审阅定稿。
 */
import { ref } from 'vue'

const visible = ref(false)
const title = ref('用户协议与隐私说明')

const show = (name) => {
    title.value = name ? `${name}` : '用户协议与隐私说明'
    visible.value = true
}

defineExpose({ show })
</script>

<style scoped lang="scss">
.policy-body {
    max-height: 62vh;
    overflow-y: auto;
    padding-right: 6px;
    font-size: 13.5px;
    line-height: 1.85;
    color: var(--nd-text-2);

    section {
        margin-bottom: 16px;
    }

    h4 {
        margin: 0 0 6px;
        font-size: 14px;
        font-weight: 600;
        color: var(--nd-text-1);
    }

    ul {
        margin: 0;
        padding-left: 18px;
    }

    li {
        margin-bottom: 4px;
    }

    b {
        color: var(--nd-text-1);
    }
}

.policy-lead {
    margin: 0 0 16px;
    padding: 10px 12px;
    border-radius: var(--nd-radius-sm);
    background: var(--nd-surface-soft);
    color: var(--nd-text-1);
}

.policy-note {
    margin: 6px 0 0;
    color: var(--nd-text-3);
    font-size: 12.5px;
}

.policy-strong {
    margin: 8px 0 0;
    padding: 8px 12px;
    border-left: 3px solid var(--nd-warning);
    border-radius: 0 var(--nd-radius-sm) var(--nd-radius-sm) 0;
    background: var(--nd-warning-bg);
    color: var(--nd-text-1);
}

.policy-foot {
    margin: 4px 0 0;
    font-size: 12.5px;
    color: var(--nd-text-3);
}
</style>
