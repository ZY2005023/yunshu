import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'userInfo'

/**
 * 当前登录用户。
 *
 * 为什么要有这个 store：原来 `userInfo` 只存在 localStorage 里，
 * 各组件各自 `JSON.parse` 一份。结果是「在个人中心改完昵称，导航栏还显示旧名字」——
 * 因为布局组件不会因为子路由切换而重新挂载。
 *
 * localStorage 仍是持久化载体（刷新后还在），store 只是让同一份数据在所有组件间**响应式**共享。
 */
export const useUserStore = defineStore('user', () => {
    const userInfo = ref({})

    /** 从 localStorage 恢复。布局挂载时调一次。 */
    const loadFromStorage = () => {
        const raw = localStorage.getItem(STORAGE_KEY)
        try {
            userInfo.value = raw ? JSON.parse(raw) : {}
        } catch {
            // 存的内容坏了就当作未登录，不要让它把页面炸掉
            userInfo.value = {}
        }
        return userInfo.value
    }

    /** 写入并同步 localStorage。登录成功、拉到最新资料、改完资料时调。 */
    const setUserInfo = (info) => {
        userInfo.value = info || {}
        localStorage.setItem(STORAGE_KEY, JSON.stringify(userInfo.value))
    }

    const clear = () => {
        userInfo.value = {}
        localStorage.removeItem(STORAGE_KEY)
    }

    return { userInfo, loadFromStorage, setUserInfo, clear }
})
