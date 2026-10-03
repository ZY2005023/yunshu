# 云舒 · AI 心理健康助手

面向高校的 AI 心理健康助手：为学生提供随手可用的情绪陪伴与心理自助工具，
帮助学校心理中心打通「风险发现 → 人工介入」的处置链路。

> ⚠️ 本系统由 AI 提供内容支持，不能替代专业心理诊疗或医疗诊断。若你或他人正面临生命危险，请立即拨打 120 / 110。

## 项目简介

云舒是一套可私有化部署的校园心理健康支持系统，覆盖从自助到干预的完整链路：

- **学生侧**：随时可用的 AI 倾诉陪伴、每日情绪日记、标准化心理测评、心理科普知识库；
- **学校侧**：自动化的风险识别与预警、工单式危机处置工作台、数据看板与用户管理；
- **AI 能力**：对话与内容分析由大模型驱动（默认 DeepSeek，兼容 OpenAI 协议的任意服务），
  回答会检索校方自建的知识库并标注引用来源。

风险识别采用**规则层 + 模型层**双通道：规则层的关键词分级检测不依赖大模型可用性；
PHQ-9 自伤项一经命中，无论总分高低都强制生成预警。识别到的危机事件可通过 Webhook
推送到值班群（企业微信 / 钉钉 / 飞书），确保「发现了」不等于「没人知道」。

## 功能特性

**学生端**

- **AI 心理咨询** —— 流式对话（SSE）、多轮记忆、意图路由（危机 / 评估 / 转介 / 资源 / 知识五类 Agent）
- **情绪日记** —— 每日心情记录、情绪月历、连续记录天数、AI 情绪分析
- **心理测评** —— PHQ-9 / GAD-7 标准化量表，自伤项命中强制预警
- **知识库** —— 分类文章 + RAG 检索（对话回答自动引用知识库并附来源）
- **个人中心** —— 资料维护、修改密码

**管理端**

- **危机预警工作台** —— 三级风险检测、结构化处置清单、跟进记录、一键跳转原始对话 / 日记
- **数据分析看板** —— 用户 / 内容规模、情绪趋势（无记录日不画 0）、活跃度
- **用户管理** —— 分页检索、启用 / 禁用（即时吊销令牌）、重置密码
- **知识内容管理** —— 富文本编辑、文档导入（txt / md / docx / pdf）、RAG 索引重建
- **API 管理** —— AI 服务地址 / 模型 / 密钥在页面上修改，保存即时生效，一键连通测试

**安全与可靠性**

- JWT 双令牌 + 吊销黑名单；bcrypt 密码哈希；登录与 AI 接口限流
- 危机事件 Webhook 主动通知；生产环境启动自检拒绝带病配置上线
- 全站 `v-html` 内容过 HTML 白名单清洗；隐私声明如实披露第三方 AI 服务与管理端可见范围

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI · SQLAlchemy 2.0 · Alembic · PyJWT · bcrypt · openai SDK |
| 前端 | Vue 3.5 · Vite · Element Plus · Pinia |
| AI | DeepSeek（兼容 OpenAI 协议，`base_url` 可替换为任意兼容服务） |
| 数据库 | MySQL 8（测试跑 SQLite 内存库，不依赖真库） |
| 测试 | pytest 431 项 · vitest 159 项 · Playwright 浏览器走查 |

## 快速开始

### 环境要求

- Python ≥ 3.12
- Node.js ≥ 18
- MySQL 8.0（本地开发用 Docker 起一个即可）

### 1. 后端

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .   # Windows；Linux/macOS 用 .venv/bin/python -m pip

cp .env.example .env                  # 填 DB_PASSWORD、JWT_SECRET、AI_API_KEY、CRISIS_WEBHOOK_URL
```

### 2. 建表

```bash
cd deploy && docker compose up -d mysql
cd ../apps/api && .venv/Scripts/python.exe -m alembic upgrade head
```

### 3. 启动

```bash
# 后端（http://localhost:1236，接口文档 /docs）
cd apps/api && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 1236

# 前端（http://localhost:5173，已配好 /api 代理）
cd apps/web && npm install && npm run dev
```

Windows 下也可以直接双击 **`启动云舒.cmd`**（停止：`停止云舒.cmd`）。

### 4. 生产部署

```bash
npm --prefix apps/web run build       # 产出 apps/web/dist
cd deploy && docker compose up -d     # FastAPI 同源托管前端产物
```

生产环境请设置 `APP_ENV=production`：启动自检会拦住占位密钥、CORS 通配、
Webhook 未配置等高风险配置（详见 `docs/上线检查清单.md`）。

## 配置说明

所有配置项见 `apps/api/.env.example`（逐项有注释），必填项：

| 变量 | 说明 |
|---|---|
| `DB_PASSWORD` | MySQL 口令 |
| `JWT_SECRET` | 令牌签名密钥，≥ 32 位随机串，**生产必改** |
| `AI_API_KEY` | 大模型服务 Key（也可登录管理后台在「API 管理」页配置，优先级更高） |
| `CRISIS_WEBHOOK_URL` | 危机预警推送地址；**留空 = 检测到风险也没有任何人被通知** |

## 测试

```bash
# 后端单元测试（SQLite 内存库，不依赖 MySQL）
cd apps/api && .venv/Scripts/python.exe -m pytest

# 前端单元测试
cd apps/web && npm test

# 端到端（真实后端 + MySQL）
apps/api/.venv/Scripts/python.exe scripts/e2e_full.py

# 浏览器走查（逐页截图 + 控制台错误汇总）
cd apps/api && .venv/Scripts/python.exe ../../scripts/ui_walkthrough.py
```

## 项目结构

```
mental-health-py/
├── apps/
│   ├── api/                FastAPI 后端
│   │   ├── app/            core / routers / services / models / schemas
│   │   ├── alembic/        数据库迁移（唯一事实来源）
│   │   └── tests/          pytest 测试
│   └── web/                Vue 3 前端（用户端 + 管理端）
├── deploy/                 docker-compose + nginx
├── docs/                   上线检查清单 / 开发记录 / Apifox 导入文件
├── scripts/                e2e、OpenAPI 导出、数据库备份、浏览器走查
├── database/               建表 SQL（历史参考，实际以 Alembic 为准）
└── 启动云舒.cmd / 停止云舒.cmd
```

## 文档

| 文档 | 说明 |
|---|---|
| `docs/上线检查清单.md` | 部署前的逐项核对清单 |
| `docs/开发记录.md` | 工程日志：接口兼容约定、设计约束、逐日修复记录 |
| `docs/openapi-apifox.json` | Apifox 可直接导入的接口文档（改接口后重跑 `make api-docs` 再导入） |

## 免责声明

本项目为心理健康自助与辅助工具，不构成医学诊断，也不能替代专业心理治疗。
部署方需自行确保：危机干预流程有真人值守、求助热线号码经当地心理机构核验、
隐私政策与知情同意经校方 / 法务确认。
