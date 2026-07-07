<div align="center">

# OpenKeyHub

**学校统一配 Key，分发给老师 —— 一个轻量的多租户 OpenAI 兼容 API 转发网关。**

管理员在后台填各家大模型的真实 Key，给每位老师发一个网关 Key；老师只填「服务地址 + 个人 Key」即可调用学校统一配置的大模型。**只转发请求、不跑渲染，老师不用自己掏钱。**

开源 · 本地部署 · 苹果风后台 · 使用门槛低

<p>
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/version-v1.1.0-5B5BD6" alt="v1.1.0">
</p>

🌐 **[在线介绍页 →](https://bubailai.github.io/OpenKeyHub/)**

</div>

---

## ✨ 这是什么

很多学校想给老师统一提供大模型能力，但：整套 AI 应用部署在校服务器会有渲染/算力排队压力；让每位老师自己买 API 又麻烦又费钱。

**OpenKeyHub 把「大模型调用」这一层单独抽出来**：学校服务器只跑这个轻量网关（纯转发、几乎不耗资源），管理员配好各家 Key、给老师发 Key；像 [Any2Manim](https://github.com/buBailai/Any2Manim) 这样的本地工具，渲染等重活仍在老师本机完成，调用大模型时走学校网关。**不排队、不掏钱、老师零门槛。**

> 配套 Any2Manim 校园场景，但本身是通用基础设施 —— 任何支持 OpenAI 格式 API 的软件都能用。

## 🎯 核心特性

- **OpenAI 兼容转发** —— `/v1/chat/completions`（含流式）+ `/v1/models`，老师端当普通 OpenAI 接口填即可。
- **国内厂家预设** —— DeepSeek、豆包/火山方舟、通义千问、智谱 GLM、硅基流动、Kimi、OpenAI、Ollama、自定义，一键填地址，只需粘 Key。
- **老师账号管理** —— 单建 / **CSV 批量导入**（姓名,手机号,备注），每人一个 Key，可启停、重置、导出名单。
- **老师自助门户** —— 老师在 `/portal` 用**手机号 + 默认密码**登录，首登强制改密后自助查看自己的 Key，管理员无需逐个分发；忘记密码可一键重置。
- **调用统计** —— 每位老师调用次数、按模型汇总、token 用量（尽力统计）、调用日志。
- **可选限额/限速** —— 默认不限制，可按账号单独开。
- **在线更新** —— 后台「更新」页一键检查 / 下载 / 重启升级；只换程序本体，数据与配置原样保留，升级前自动备份可回滚。
- **苹果风后台** —— 浅色、圆角、毛玻璃，自适应深色模式，开箱即用。
- **轻** —— FastAPI + SQLite + 4 个依赖，本地部署一条命令起，数据全在本地。

## 🚀 快速开始

```bash
# 1. 启动（首次会自动建虚拟环境装依赖）
./start.sh
#   或手动：
#   python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
#   ./.venv/bin/python -m backend.main
```

启动后终端会打印三个地址：
- **管理后台**：`http://127.0.0.1:8011/` —— 首次打开设置管理员账号密码。
- **局域网地址**：`http://<本机IP>:8011/` —— 校内其他电脑访问后台用。
- **老师填的地址**：`http://<本机IP>:8011/v1` —— 连同各自的 Key 发给老师。

### 管理员三步走

1. **加厂家**：后台 →「厂家」→ 选预设（如 DeepSeek）→ 粘真实 Key → 填要开放的模型。
2. **发老师**：后台 →「老师」→ 新建 / 批量导入 → 拿到每人的 Key（**只显示一次**，可下载 CSV）。
3. 把 `服务地址/v1` + 老师的 Key 发下去。

### 老师怎么用

1. 浏览器打开学校给的老师端地址 `http://学校IP:8011/portal`，用**手机号 + 默认密码 openkeyhub** 登录，按提示改密，看到自己的 Base URL 和 API Key（可一键复制）。
2. 在任意支持 OpenAI 接口的 AI 客户端里，厂商 / 接口类型选「OpenAI 兼容」或「自定义」→ Base URL 填 `http://学校IP:8011/v1`，API Key 填自己的 Key，模型填开放的名字（如 `deepseek-chat`）→ 正常使用。

## 🧱 技术架构

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + httpx（异步流式转发） |
| 存储 | SQLite 单文件 |
| 后台前端 | 纯 HTML/CSS/JS，无构建；苹果风 UI |
| 鉴权 | 老师 Key 存哈希；管理员密码 PBKDF2；签名 cookie 会话 |

```
API共享/
├── backend/      # 网关 + 后台 API + 存储
│   ├── gateway.py   # /v1/* 转发核心
│   ├── admin.py     # 后台 API
│   ├── portal.py    # 老师端自助门户 API
│   ├── store.py     # SQLite
│   ├── auth.py providers.py usage.py config.py main.py
├── frontend/     # 苹果风后台(index/app) + 老师端(portal)
├── data/         # 运行数据（db / 密钥，gitignore）
└── start.sh
```

## 🔒 安全

- 真实厂家 Key 与老师 API Key **在库内加密存储**（HMAC 认证加密，密钥派生自 `data/secret.key`）；后台只显示掩码，明文仅老师本人登录可见。
- 老师 Key 同时存哈希用于网关校验；管理员可随时重置 Key / 登录密码 / 停用账号。
- 建议**仅部署在校内局域网**；对外暴露请加 HTTPS 反代与网段白名单。
- 备份提示：`data/secret.key` 是解密钥匙，请连同 `data/*.db` 一起备份；丢失则已加密字段不可恢复（重置 Key 即可重建）。

## 📜 许可证

[MIT](LICENSE) © buBailai

> 与 [OpenMentor](https://github.com/buBailai/OpenMentor) / [Any2Manim](https://github.com/buBailai/Any2Manim) 同属本地部署、数据自主的工具族。
