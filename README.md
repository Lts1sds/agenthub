# AgentHub

Agent 分发平台：创作者打包上传 agent，消费者一键安装使用；agent 的 LLM 调用统一走你的中转站（OpenAI 兼容接口）按 token 计费。

组成：
- `agenthub` CLI —— 创作者上传（push）、消费者安装（install/run）
- `server.py` —— 市场服务端（Flask + SQLite）：上传 API、市场网页、一键安装脚本生成、下载计数

## 消费者：三种使用方式

```bash
# 方式一：命令行（2 条命令）
agenthub market set https://your-market.com
agenthub install my-agent

# 方式二：网页一键安装 —— 市场网页每个 agent 有
#   "Windows 一键安装 (.bat)" 按钮，下载后双击即装（自动装 CLI + agent）

# 方式三：program 型 agent 装完后双击启动器
#   ~/.agenthub/run-<name>.bat
```

## 创作者：上传 agent

```bash
# 1. 按规范做好包（见下方包规范）
# 2. 配置市场与上传 token
agenthub market set https://your-market.com
agenthub login --base-url https://your-relay.com/v1 --api-key sk-xxx --upload-token YOUR_TOKEN

# 3. 上传
agenthub push ./my-agent
# 或临时指定 token
agenthub push ./my-agent --token YOUR_TOKEN
```

## 部署市场服务端

```bash
pip install flask
AGENTHUB_PUBLIC_URL=https://your-market.com \
AGENTHUB_UPLOAD_TOKEN=your-secret-token \
python server.py          # 默认端口 18766
```

- 数据落在 `data/`（SQLite + 包 zip），环境变量 `AGENTHUB_SERVER_DATA` 可改
- `AGENTHUB_UPLOAD_TOKEN` 是创作者上传凭据；`AGENTHUB_PUBLIC_URL` 用于生成消费者安装命令/脚本
- 生产部署建议放 nginx/HTTPS 之后

## Agent 包规范

每个 agent 是一个目录，必须有 `agent.yaml` 清单：

```yaml
name: my-agent          # 小写字母/数字/连字符
version: 0.1.0          # x.y.z
author: your-name
description: 一句话描述
type: prompt-pack       # prompt-pack | program
models:                 # 声明所需模型（经中转站调用）
  - deepseek-chat
```

### type: prompt-pack（轻量，装进已有 agent 运行时）

```yaml
install:
  targets:
    - comagic
    - claude-code
```

包内放 `skills/<skill-name>/SKILL.md`，安装时自动注入对应运行时的 skills 目录。
`AGENTS.md` 是包的说明文档，随包分发。

### type: program（独立程序）

```yaml
runtime:
  kind: python-cli      # python-cli | mcp | node（当前支持 python-cli）
  entry: app/main.py
  deps: requirements.txt
```

- 有依赖时自动创建 venv 并安装
- 运行时自动注入环境变量 `AGENTHUB_BASE_URL` / `AGENTHUB_API_KEY`，程序内直接读这两个变量调中转站
- 零依赖包可跳过 requirements.txt

## 命令一览

| 命令 | 说明 |
|---|---|
| `agenthub login --base-url URL --api-key KEY [--upload-token T]` | 保存中转站凭据 / 上传 token |
| `agenthub market set <path 或 http://...>` | 设置市场源（本地目录或市场服务端） |
| `agenthub push <dir> [--token T]` | 创作者上传包到远程市场 |
| `agenthub list` / `info <name>` | 浏览市场 |
| `agenthub install <name> [--force]` | 安装 |
| `agenthub run <name> [args...]` | 运行 program 型 agent |
| `agenthub installed` / `uninstall <name>` | 管理已装 agent |

## 路线图

- P0（当前）：包规范 + CLI + 市场服务端（上传/网页/一键安装脚本/下载计数），全链路已 e2e 验证
- P1：发布 PyPI（一键脚本里的 `pip install agenthub-cli` 生效）+ 用户注册发 key（对接中转站子令牌）+ 用量统计分成
- P2：托管运行（网页直用）+ 评价排行 + 私有 agent
