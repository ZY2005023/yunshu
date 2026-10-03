# AI 心理健康助手（Mental Health Assistant）

基于 **Spring Boot 3 + Spring AI + Vue 3** 的全栈 AI 心理咨询系统。用户注册登录后可创建咨询会话，与大模型进行**流式（SSE）心理对话**，对话记录持久化保存。

> 本项目为 AI 全栈学习项目，同时作为**接口自动化测试框架的被测系统**使用。

---

## 技术栈

### 后端（Java 21）
| 组件 | 说明 |
|---|---|
| Spring Boot 3.5 | 核心框架，内嵌 Tomcat（端口 `1236`） |
| Spring AI 1.0 | 大模型接入层（OpenAI 兼容协议） |
| MyBatis-Plus | ORM，读写 MySQL |
| MySQL 8 | 业务数据库（库名 `mental_health_assistant`） |
| Spring Security + JWT | 登录认证与接口鉴权 |
| SSE（Server-Sent Events） | AI 回复流式推送 |

### 前端（Node.js ≥18）
| 组件 | 说明 |
|---|---|
| Vue 3 + Vite | 核心框架与构建工具 |
| Element Plus | UI 组件库 |
| Pinia / Vue Router | 状态管理 / 路由 |
| Axios | HTTP 请求 |
| ECharts | 数据图表 |

---

## 项目结构

```
mental-health/
├── env/                      # 项目专属环境（Maven 本体 + 依赖仓库 + 镜像配置）
│   ├── maven/                #   Maven 3.9.16（由 mvnw 自动管理）
│   ├── repository/           #   本地依赖仓库（等价于 Python 的 venv/site-packages）
│   └── settings.xml          #   阿里云 Maven 镜像配置
├── backend/                  # 后端（Java 21 + Spring Boot 3）
│   ├── src/main/java/
│   │   └── controller/       #   接口层：用户、AI 心理对话
│   │   ├── AiService/        #   AI 能力层：Prompt 管理、结构化输出
│   │   ├── entity/           #   实体：User / ConsultationSession / ConsultationMessage
│   │   ├── service/          #   业务层
│   │   └── mapper/           #   数据访问层
│   ├── src/main/resources/
│   │   └── application.yml   #   核心配置（数据库 / AI 服务 / 端口）
│   ├── start-backend.sh      #   一键启动脚本（自动使用 env/ 环境）
│   └── start-backend.cmd     #   Windows 双击版
└── frontend/                 # 前端（Vue 3 + Vite）
    ├── src/                  #   页面 / 组件 / 路由 / 状态
    └── start-frontend.cmd    #   一键启动脚本
```

---

## 接口概览

统一前缀 `/api`，除登录注册外均需携带 JWT Token。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/user/add` | 用户注册 |
| POST | `/api/user/login` | 用户登录，返回 JWT Token |
| GET | `/api/user/current` | 获取当前登录用户信息 |
| POST | `/api/psychological-chat/session/start` | 创建咨询会话 |
| POST | `/api/psychological-chat/stream` | **AI 流式对话（SSE）**，实时返回咨询回复 |

---

## 环境准备

| 依赖 | 版本要求 | 说明 |
|---|---|---|
| JDK | 21+ | 后端运行环境 |
| Node.js | ≥18 | 前端构建运行 |
| MySQL | ≥8.0 | 业务数据存储 |
| 大模型 API | — | 任意 OpenAI 兼容服务（推荐硅基流动 / DeepSeek / 智谱） |

> Maven 无需安装：项目内置 `mvnw` 包装器，首次运行自动使用 `env/maven` 中的本地 Maven 与依赖仓库，**零全局污染**。

---

## 快速启动

### 1. 初始化数据库

```sql
CREATE DATABASE mental_health_assistant DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
导入 `mental_health_assistant.sql`（9 张表，含种子用户数据）。

### 2. 配置大模型服务

编辑 `backend/src/main/resources/application.yml`：

```yaml
ai:
  openai:
    chat:
      options:
        model: deepseek-ai/DeepSeek-V3    # 模型名，随服务商调整
    api-key: sk-xxxxxxxx                  # ← 替换为你的 API Key
    base-url: https://api.siliconflow.cn  # ← 服务商地址，可替换
```

支持任意 OpenAI 兼容服务商（硅基流动 / DeepSeek 官方 / 智谱 GLM / 本地 Ollama），**仅需修改以上配置，无需改动代码**。

### 3. 启动后端（端口 1236）

```bash
# Windows：双击 backend/start-backend.cmd
# 或命令行：
cd backend
./start-backend.sh
```

验证：浏览器访问 `http://127.0.0.1:1236`，出现 403（Spring Security 拦截）即为启动成功。

### 4. 启动前端

```bash
# 首次需安装依赖（node_modules 装在项目内，不动全局）
cd frontend
npm install

# Windows：双击 start-frontend.cmd，或
npm run dev
```

浏览器访问 `http://localhost:5173`。

### 5. 默认账号

数据库自带种子用户（见 `user` 表），或直接通过注册接口新建。

---

## 项目环境说明（env/）

本项目采用**项目级隔离环境**，不污染系统全局目录：

| 目录 | 等价概念 | 内容 |
|---|---|---|
| `env/maven/` | Maven 安装目录 | Maven 3.9.16 本体 |
| `env/repository/` | Python 的 venv/site-packages | 全部 Java 依赖 jar |
| `env/settings.xml` | pip 源配置 | 阿里云 Maven 镜像 |

启动脚本已自动注入 `MAVEN_USER_HOME` 与 `maven.repo.local`，删除 `env/` 即等于清空全部 Java 环境，可随时重建。

---

## 测试说明

本项目同时作为 **AI 增强接口自动化测试框架的被测系统**：

- 标准业务接口（注册/登录/会话管理）→ 常规数据驱动用例 + 数据库断言
- AI 流式接口（SSE 对话）→ 流式响应测试、超时控制、内容断言等进阶场景
- 测试框架代码位于上层工作区 `ai-api-test/`（Python + pytest，环境为 `ai-api-test/venv`）
