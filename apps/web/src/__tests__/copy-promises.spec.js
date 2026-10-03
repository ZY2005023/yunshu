/**
 * 文案守卫：**不准承诺代码做不到的事**。
 *
 * 为什么专门写这个测试文件：
 * 改版时手写文案，很容易顺手把「应该有的功能」当「已有功能」写出去。
 * 2026-10-02 一次排查就抓出 6 处，例如：
 *   · 品牌区写「内容加密存储」——后端其实**没有任何内容加密**（字段是明文 Text）
 *   · 写「对话与日记仅你本人可见」——管理端「情绪日志」页能读到全部用户日记正文
 *   · 写「不会向第三方披露」——对话与日记确实会发给第三方 AI 服务
 *   · 写「用于接收通知」——项目里没有任何发信机制
 *   · 写「仅用于紧急联系」——没有任何紧急联系机制
 *   · 写「可收藏、可回顾」——收藏功能未实现
 *
 * 这类问题的共同点是：**构建通过、单测通过、页面也正常渲染**，只有对着代码看才发现。
 * 所以只能靠这组断言把已知的几个坑钉住。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

/**
 * 剥掉注释再校验。
 *
 * 必须这么做：这些文件的注释里正是在**讨论**那些错误的说法
 * （例如「原来写过『内容加密存储』，这是做不到的」），
 * 不剥离的话断言会把注释当成文案，得到假失败。
 */
const stripComments = (src) =>
    src
        .replace(/<!--[\s\S]*?-->/g, '') // 模板注释
        .replace(/\/\*[\s\S]*?\*\//g, '') // 块注释 / JSDoc
        .replace(/^[ \t]*\/\/.*$/gm, '') // 行注释

const read = (rel) => stripComments(fs.readFileSync(path.resolve(here, '..', rel), 'utf-8'))

const POLICY = read('components/PolicyDialog.vue')
const AUTH_LAYOUT = read('components/AuthLayout.vue')
const FRONTEND_LAYOUT = read('components/FrontendLayout.vue')
const LOGIN = read('views/login.vue')
const REGISTER = read('views/register.vue')
const HOME = read('views/home.vue')
const PROFILE = read('views/profile.vue')
const CRISIS = read('views/crisis.vue')
const CONSULTATIONS = read('views/consultations.vue')

/** 所有面向用户的文案文件 */
const ALL_COPY = [
    POLICY,
    AUTH_LAYOUT,
    FRONTEND_LAYOUT,
    LOGIN,
    REGISTER,
    HOME,
    PROFILE,
    CRISIS,
    CONSULTATIONS
].join('\n')

describe('不得出现的假承诺', () => {
    it('不声称内容加密 —— 后端没有做任何内容加密', () => {
        expect(ALL_COPY).not.toMatch(/内容加密|加密存储|加密保存/)
    })

    it('不声称「仅你可见」—— 管理端能读取全部用户内容', () => {
        // 2026-10-03 收紧：home.vue 一度写「对话内容仅你可见」，差两个字
        // 绕过了旧正则 /仅你本人可见/。正确表述是「仅你与校心理老师可见」，
        // 后面跟的是「与」而不是「可见」，不会被这条误伤。
        expect(ALL_COPY).not.toMatch(/仅你(本人)?可见/)
        expect(ALL_COPY).not.toMatch(/(?<!不是)只有你(一个人)?(能)?看到/)
        // 正确口径必须在首页出现 —— 与 AuthLayout 的披露保持同一标准
        expect(HOME).toContain('仅你与校心理老师可见')
    })

    it('不声称「不会向第三方披露」—— 内容会发给第三方 AI 服务', () => {
        expect(ALL_COPY).not.toContain('不会向第三方披露')
        expect(ALL_COPY).not.toContain('不向第三方披露')
    })

    it('不声称邮箱用于接收通知 —— 项目里没有任何发信机制', () => {
        expect(ALL_COPY).not.toMatch(/接收通知|邮件通知|短信通知/)
    })

    it('不声称手机号用于紧急联系 —— 该字段存了从未被使用', () => {
        expect(ALL_COPY).not.toMatch(/紧急联系|紧急联络/)
    })

    it('不承诺收藏功能 —— user_favorite 表未被任何代码引用', () => {
        expect(ALL_COPY).not.toMatch(/可收藏|收藏文章|我的收藏/)
    })

    it('不承诺导出 / 注销 —— 均未实现', () => {
        expect(ALL_COPY).not.toMatch(/导出(我的)?(数据|记录)|一键导出/)
    })

    it('不虚报风险分级数量 —— 系统只有 3 级', () => {
        // core/crisis.py 只有 LEVEL_ATTENTION(1) / LEVEL_WARNING(2) / LEVEL_CRITICAL(3)，
        // 首页一度写成「4 级风险识别分级」；通知器里也一度有个不存在的「4 级 · 紧急」
        expect(ALL_COPY).not.toMatch(/4\s*级/)
    })
})

describe('界面承诺必须有对应的实现', () => {
    it('咨询记录页若声称可检索，就必须真的挂了搜索组件', () => {
        if (CONSULTATIONS.includes('检索')) {
            expect(CONSULTATIONS).toContain('TableSearch')
        }
    })

    it('危机页若声称按风险排序，后端就必须真的按等级排', () => {
        if (CRISIS.includes('按风险等级排序')) {
            const svc = fs.readFileSync(
                // here = src/__tests__/，后端在 apps/api/，要退三级：
                // src/__tests__ → src → apps/web → apps，再进 api/
                path.resolve(
                    here,
                    '../../../api/app/services/crisis.py'
                ),
                'utf-8'
            )
            expect(svc).toMatch(/order_by\([^)]*level/)
        }
    })
})

describe('管理端页面不得读取后端不存在的字段', () => {
    // 这一类 bug **不会报错**：字段取不到就是 undefined，渲染成空白，
    // 构建、单测、页面渲染全都拦不住（见 MEMORY.md「静默失效」）。
    // 2026-10-02 修的就是这两个：头像列恒空、时间列整列空白。

    it('咨询记录页不再读 userNickname —— 后端给的是 nickname / username', () => {
        expect(CONSULTATIONS).not.toContain('userNickname')
    })

    it('咨询记录页不再读 lastMessageTime —— 后端给的是 startedAt', () => {
        expect(CONSULTATIONS).not.toContain('lastMessageTime')
    })

    it('危机工单列表必须显示用户身份，不能只给一个用户 ID', () => {
        // 原来详情里只有「用户ID: 52」，管理员没法知道是谁
        expect(CRISIS).toMatch(/nickname|username/)
    })

    it('危机工单处置必须带结构化措施，不能只有一个备注框', () => {
        expect(CRISIS).toContain('measures')
    })
})

describe('隐私说明必须包含的披露', () => {
    it('说明它不是医疗诊断工具', () => {
        expect(POLICY).toMatch(/不提供医学诊断/)
    })

    it('说明内容会发送给第三方 AI 服务', () => {
        expect(POLICY).toContain('第三方 AI 服务')
    })

    it('明确写出「不是只有你一个人能看到」', () => {
        expect(POLICY).toContain('不是只有你一个人')
    })

    it('说明心理老师可以在管理后台查看', () => {
        expect(POLICY).toMatch(/心理老师|管理员/)
        expect(POLICY).toContain('管理后台')
    })

    it('说明风险情形会生成记录（而不是承诺即时救援）', () => {
        expect(POLICY).toContain('风险记录')
        // 必须明确否认它是急救通道
        expect(POLICY).toMatch(/不是紧急救援通道/)
    })

    it('给出真实的求助渠道', () => {
        expect(POLICY).toContain('12356')
        expect(POLICY).toContain('120')
        expect(POLICY).toContain('110')
    })

    it('如实说明没有自助导出/注销', () => {
        expect(POLICY).toMatch(/没有提供自助导出|没有提供.*自助注销/)
    })
})

describe('入口只指向真实存在的页面', () => {
    it('头像兜底文案不是「个人中心」（曾经误导为可点击的页面名）', () => {
        expect(FRONTEND_LAYOUT).not.toMatch(/\|\|\s*'个人中心'/)
    })

    it('登录页提到的「个人中心 → 修改密码」确实存在', () => {
        // 文案里引用了个人中心，就必须真的有这个页面与这个功能
        if (LOGIN.includes('个人中心')) {
            expect(fs.existsSync(path.resolve(here, '../views/profile.vue'))).toBe(true)
            expect(PROFILE).toMatch(/修改密码/)
        }
    })
})
