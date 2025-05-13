# OnDemand-API-Proxy 代理(模型来源自Playground升级质量)

一款基于 Flask 的 API 代理，连接你的客户端 (只测试了 Cherry Studio) 支持多个模型，管理多轮对话。

## 功能

- **兼容 OpenAI API**：提供标准 `/v1/models` 和 `/v1/chat/completions` 接口。
- **支持多个模型**：如 GPT-4o, Claude 3.7 Sonnet, Gemini 2.0 Flash 等。
- **多轮对话**：用 Session ID 保持对话的上下文。
- **账户轮换**：轮流使用多个 on-demand.io 账户，平衡负载。
- **会话超时**：10 分钟无活动后，自动重置会话或切换账户。
- **Docker 支持**：轻松部署到 Hugging Face Spaces。

## 使用方法

### 准备工作

1. 准备好你的 on-demand.io 账户 (邮箱和密码)。
2. 如果本地运行，请安装依赖 (见“本地部署”)。

### 接口

- **模型列表**: `GET /v1/models`
  - 返回可用模型列表。
- **聊天**: `POST /v1/chat/completions`
  - 发送聊天请求，支持流式和非流式响应。

### 模型列表 (部分)

- `gpt-4o`
- `claude-3.7-sonnet`
- `gpto3-mini`
- `gpt-4o`
- `gpt-4.1`
- `gpt-4.1-mini`
- `gpt-4.1-nano`
- `gpt-4o-mini`
- `deepseek-v3`
- `deepseek-r1`
- `gemini-2.0-flash`

### 如何部署

**Hugging Face Spaces 部署 (推荐)**

1. **创建 Hugging Face 账户**: [https://huggingface.co/](https://huggingface.co/)
2. **创建 Space**:
   - 点击 [这里创建新的 Space](https://huggingface.co/new-space)。
   - 填写 Space 名称。
   - **重要**: 选择 `Docker` 作为 Space 类型。
   - 设置权限 (公开或私有)，然后创建!
3. **上传代码**:
   - 将以下文件上传到你 Space 的代码仓库：
     - `2api.py` (主程序)
     - `requirements.txt` (依赖列表)
     - `Dockerfile` (Docker 配置文件)

4. **配置账户信息 (重要!)**:
   - 进入你 Space 的“Settings” (设置) -> “Repository secrets” (仓库密钥)
   - 添加一个名为 `ONDEMAND_ACCOUNTS` 的 Secret
   - 它的值是一个 JSON 字符串，包含你的 on-demand.io 账户信息:

     ```json
     {
       "accounts": [
         {"email": "你的邮箱1@example.com", "password": "你的密码1"},
         {"email": "你的邮箱2@example.com", "password": "你的密码2"}
       ]
     }
     ```

     **注意**: 这样更安全！把账号信息直接写进代码是很危险的。

5. **完成**:
   - Hugging Face 会自动构建 Docker 镜像并部署你的 API!
   - 访问你的 Space URL (如 `https://你的用户名-你的space名称.hf.space`) 即可使用。

**完成!**

现在，你就可以用 Cherry Studio 连接到你的 API，享受多账户轮询和会话管理了！

**任何问题?** 欢迎提问!
