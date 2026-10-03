/**
 * 前端改版的基础保障测试。
 *
 * 为什么要单独测这些：
 *  - 改版动了全局样式与布局组件，最容易出问题的地方是「设计令牌被删/改名」
 *    和「基础件渲染不出来」。这类问题在类型检查和构建阶段都发现不了，
 *    只有真的挂载一次、读一次 CSS 才能确认。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import BrandLogo from '../components/BrandLogo.vue'
import UserAvatar from '../components/UserAvatar.vue'

const here = path.dirname(fileURLToPath(import.meta.url))
const styleCss = fs.readFileSync(path.resolve(here, '../style.css'), 'utf-8')

describe('基础展示件', () => {
    it('BrandLogo 渲染品牌名与副标题', () => {
        const w = mount(BrandLogo, {
            props: { title: '云舒', subtitle: 'AI 心理健康助手' }
        })
        expect(w.text()).toContain('云舒')
        expect(w.text()).toContain('AI 心理健康助手')
    })

    it('BrandLogo iconOnly 时不渲染文字', () => {
        const w = mount(BrandLogo, { props: { iconOnly: true } })
        expect(w.text()).toBe('')
    })

    it('UserAvatar 无头像时用昵称首字兜底（中文）', () => {
        const w = mount(UserAvatar, { props: { name: '张三' } })
        expect(w.text()).toBe('张')
        // 不能再依赖外链占位图
        expect(w.find('img').exists()).toBe(false)
    })

    it('UserAvatar 英文名取首字母并大写', () => {
        const w = mount(UserAvatar, { props: { name: 'alice' } })
        expect(w.text()).toBe('A')
    })

    it('UserAvatar 名称为空时给出默认字符，不渲染空白', () => {
        const w = mount(UserAvatar, { props: { name: '' } })
        expect(w.text()).toBe('心')
    })

    it('UserAvatar 传了头像地址时渲染 img', () => {
        const w = mount(UserAvatar, { props: { name: '张三', src: '/a.png' } })
        expect(w.find('img').attributes('src')).toBe('/a.png')
    })

    it('UserAvatar 同一 seed 的颜色稳定（不会每次刷新变色）', () => {
        const a = mount(UserAvatar, { props: { name: 'x', seed: 'user-1' } })
        const b = mount(UserAvatar, { props: { name: 'y', seed: 'user-1' } })
        const colorOf = (w) =>
            w.find('.nd-avatar__initial').attributes('style') || ''
        expect(colorOf(a)).toBe(colorOf(b))
    })
})

describe('设计系统令牌', () => {
    const REQUIRED = [
        '--nd-primary-500',
        '--nd-primary-50',
        '--nd-text-1',
        '--nd-text-3',
        '--nd-border',
        '--nd-bg',
        '--nd-surface',
        '--nd-radius',
        '--nd-radius-full',
        '--nd-shadow-xs',
        '--nd-gap',
        '--nd-font',
        // 各页面用它算「视口高度减去顶栏」，删掉会导致页面高度错乱
        '--nd-navbar-h',
        '--nd-ease',
        '--nd-duration'
    ]

    it.each(REQUIRED)('声明了 %s', (token) => {
        expect(styleCss).toContain(`${token}:`)
    })

    it('覆盖了 Element Plus 的主色变量', () => {
        expect(styleCss).toContain('--el-color-primary: var(--nd-primary-500)')
    })

    it('覆盖了 Element Plus 的圆角与字体变量', () => {
        expect(styleCss).toContain('--el-border-radius-base:')
        expect(styleCss).toContain('--el-font-family:')
    })

    it('提供了页面通用工具类', () => {
        for (const cls of ['.nd-container', '.nd-card', '.nd-empty', '.nd-badge']) {
            expect(styleCss).toContain(cls)
        }
    })

    it('字体栈包含中文字体，避免中文回退到衬线体', () => {
        expect(styleCss).toMatch(/PingFang SC|Microsoft YaHei/)
    })
})
