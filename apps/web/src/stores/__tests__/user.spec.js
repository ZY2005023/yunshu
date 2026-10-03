/**
 * 当前用户 store。
 *
 * 引入它的原因是修一个真实问题：在个人中心改完昵称，导航栏还显示旧名字 ——
 * 因为布局组件不会因子路由切换而重新挂载，各组件各自解析 localStorage 得不到响应式更新。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useUserStore } from '../user'

beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
})

describe('useUserStore', () => {
    it('初始为空对象', () => {
        expect(useUserStore().userInfo).toEqual({})
    })

    it('setUserInfo 同时更新内存与 localStorage', () => {
        const store = useUserStore()
        store.setUserInfo({ id: 7, username: 'alice', nickname: '爱丽丝' })

        expect(store.userInfo.nickname).toBe('爱丽丝')
        expect(JSON.parse(localStorage.getItem('userInfo')).id).toBe(7)
    })

    it('改昵称后 store 立刻变 —— 这就是导航栏能实时刷新的原因', () => {
        const store = useUserStore()
        store.setUserInfo({ id: 7, nickname: '旧名字' })
        store.setUserInfo({ id: 7, nickname: '新名字' })
        expect(store.userInfo.nickname).toBe('新名字')
    })

    it('loadFromStorage 能从缓存恢复', () => {
        localStorage.setItem('userInfo', JSON.stringify({ id: 9, username: 'bob' }))
        const store = useUserStore()
        store.loadFromStorage()
        expect(store.userInfo.username).toBe('bob')
    })

    it('缓存内容损坏时降级为空对象，不抛异常', () => {
        localStorage.setItem('userInfo', '{不是合法 JSON')
        const store = useUserStore()
        expect(() => store.loadFromStorage()).not.toThrow()
        expect(store.userInfo).toEqual({})
    })

    it('clear 同时清内存与 localStorage', () => {
        const store = useUserStore()
        store.setUserInfo({ id: 1 })
        store.clear()

        expect(store.userInfo).toEqual({})
        expect(localStorage.getItem('userInfo')).toBeNull()
    })

    it('setUserInfo(undefined) 不炸，退化为空对象', () => {
        const store = useUserStore()
        store.setUserInfo(undefined)
        expect(store.userInfo).toEqual({})
    })
})
