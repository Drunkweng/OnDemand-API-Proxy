# OnDemand API Proxy

使用 Flask 开发的 OpenAI/OpenChat 兼容代理，支持 HuggingFace Space 上部署。内置 KEY 池，支持自动失效切换，并提供基于 Huggingface Space Secrets 的接口鉴权。

## 特性 (Features)
- **多 KEY 池轮询**：支持自动失效禁用和恢复。
- **OpenAI Chat/Completion API 支持**：兼容标准格式。
- **接口权限控制**：基于 `PRIVATE_KEY` 请求头的权限验证。
- **一键部署到 HuggingFace Spaces**。
- **多模型自动路由**：根据需求选择适配模型。

---

## 快速部署 (Quick Start)

### 1. 克隆项目 (Clone)
```bash
git clone <your-project-repo>
cd <your-project-repo>
```

### 2. 配置 Secret
在 HuggingFace Space 的 `Settings -> Secrets` 页面添加以下配置：

| 名称 (Key)      | 举例值 (Value)                | 备注 (Remark)                          |
|-----------------|------------------------------|----------------------------------------|
| `PRIVATE_KEY`   | 自定义的访问密钥，例如一段复杂的密码 | 用于接口权限验证，请勿公开。             |

### 3. 添加 OnDemand API Key
编辑 `ONDEMAND_APIKEYS` 数组，将你的可用 KEY 逐行填入（至少一个）：

```python
ONDEMAND_APIKEYS = [
    "请换为你自己的OnDemand API KEY",
    # …
]
```

### 4. 一键部署 (Deploy)
将代码推送到 HuggingFace Space，即可自动运行服务。

---

### 配置 API网址 和 PRIVATE_KEY
1. 设置 API网址
将 HuggingFace Space 自动生成的 API 网址（例如:"https://用户名-空间名.hf.space/v1"）替换到需要调用 API 的地方。

2. 配置 Secrets 中的 PRIVATE_KEY
在 HuggingFace Space 的 Settings -> Secrets 页面中，添加以下配置：

名称 (Key)	值 (Value)	备注 (Remark)
PRIVATE_KEY	自定义的访问密钥，例如一段复杂的密码	用于接口权限验证，请勿公开。

---

通过以上配置，你即可完成 API 的集成，并使用 PRIVATE_KEY 对接口权限进行有效控制！

---

## 重要说明 (Important Notice)
1. 项目仅为 API 代理，请勿存储非法内容或滥用接口。
2. 如需扩展更多路径或更改权限逻辑，请修改 `check_private_key` 函数。
3. KEY 池中的所有 Key 会周期性健康检测，失效的 Key 会自动跳过。

---

## 常见问题 (FAQ)

**Q: 如何修改超级管理员密钥？**  
A: 在 HuggingFace Space 的 Secrets 中修改 `PRIVATE_KEY` 即可，无需停服。

**Q: KEY 用完/失效会怎样？**  
A: 自动切换到下一个可用 KEY。若全部 KEY 失效，返回 `500` 状态码并间隔自动重试。

**Q: 可以支持自定义 API 路径或白名单吗？**  
A: 可以，通过修改 `check_private_key()` 函数，指定哪些路径需要或不需要鉴权。

--- 

通过本 `README`，你可以轻松快速部署和使用 OnDemand API Proxy！
