import { createApp } from 'vue'
import App from './App.vue'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import router from './router'

// caution: 引入顺序不能调换 ——
// element-plus 的样式必须先加载，项目自己的设计系统（style.css）放在最后，
// 才能用同权重选择器覆盖组件库的默认样式。
// 反过来写的话，所有主题覆盖都会静默失效。
import 'element-plus/dist/index.css'
import './style.css'

const app = createApp(App)

const pinia = createPinia()

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus).use(router).use(pinia).mount('#app')
