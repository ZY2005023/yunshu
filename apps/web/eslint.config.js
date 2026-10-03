import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import prettier from 'eslint-config-prettier'

/**
 * ESLint 扁平配置（ESLint 9+）。
 *
 * 两条取舍：
 * 1. 大部分规则设为 warn 而非 error —— 这是一份存量的老代码，如果一上来全是
 *    error，`npm run lint` 会红成一片、没人会真去看。先把护栏立起来，逐轮收紧。
 * 2. `eslint-config-prettier` 放在最后，关掉所有与 Prettier 冲突的格式规则，
 *    避免"lint 和 format 互相改对方"的来回打架。
 */
export default [
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', '*.min.js']
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node
      }
    },
    rules: {
      // 护栏类规则保持 error
      'no-debugger': 'error',
      'no-var': 'error',
      'eqeqeq': ['error', 'smart'],

      // 存量代码的渐进式规则
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
      'no-empty': ['warn', { allowEmptyCatch: true }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],

      // Vue：这条规则对页面级组件是误报，关掉
      'vue/multi-word-component-names': 'off',
      // 以下均为纯排版规则，交给 Prettier
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/attributes-order': 'off',
      'vue/require-default-prop': 'off'
    }
  },
  {
    files: ['**/*.spec.js', '**/*.test.js'],
    rules: {
      'no-console': 'off'
    }
  },
  prettier
]
