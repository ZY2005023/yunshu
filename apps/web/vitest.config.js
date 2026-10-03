import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config.js'

/**
 * 复用 vite.config.js 的别名与插件，只补测试相关配置。
 * 单独成文件是为了不把测试配置混进构建配置里。
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      // sanitize.js 依赖 DOMParser，必须有 DOM 环境
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.{spec,test}.js'],
      restoreMocks: true
    }
  })
)
