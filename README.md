OnDemand API Proxy
使用 Flask 开发的 OpenAI/OpenChat 兼容代理，支持 HuggingFace Space 上部署。内置 KEY 池，支持自动失效切换，并提供基于 Huggingface Space Secrets 的接口鉴权。

特性 Features
多 KEY 池轮询，自动失效禁用和恢复
支持 OpenAI Chat/Completion API 标准格式
基于 PRIVATE_KEY 请求头的接口权限控制
一键部署到 HuggingFace Spaces
多模型自动路由
快速部署 Quick Start
1. 克隆项目 Clone
<BASH>
git clone <your-project-repo>
cd <your-project-repo>
2. 配置 Secret
在 HuggingFace Space 的 Settings -> Secrets 页面，添加：

名称 (Key)	举例值 (Value)	备注
PRIVATE_KEY	⚠️ 请换为你自己的访问密钥，例如：自行设置一段不容易猜到的密码	你自定义的访问密钥，正式生产请勿暴露
3. 添加 OnDemand API Key
编辑 ONDEMAND_APIKEYS 数组，将你的可用 key 逐行填入（至少一个）：

<PYTHON>
ONDEMAND_APIKEYS = [
    "⚠️ 请换为你自己的OnDemand API KEY",
    # ...
]
4. 一键部署 Deploy
推送到 HuggingFace Space，即可自动运行。

API 使用方法 Usage
所有 API 调用必须加上 HTTP Header：

<TEXT>
X-API-KEY: ⚠️ 请填写你自己的PRIVATE_KEY
未携带或错误，将返回 401 Unauthorized。

典型调用示例 Example
ChatGPT Completion（同步）：

<BASH>
curl -X POST https://<space-host>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: ⚠️ 请填写你自己的PRIVATE_KEY" \
  -d '{
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'
获取模型列表：

<BASH>
curl -X GET https://<space-host>/v1/models \
  -H "X-API-KEY: ⚠️ 请填写你自己的PRIVATE_KEY"
请替换 <space-host> 为你的 HuggingFace Space 生成的地址。

重要说明 Important Notice
本项目仅为 API 代理，请勿存储非法内容或滥用接口。
如需扩展更多路径或更改权限逻辑，请修改 check_private_key 函数。
KEY池所有 Key 会周期性健康检测，失效 Key 自动跳过。
常见问题 FAQ
Q: 如何修改超级管理员密钥？
A: 在 Huggingface Space 的 Secrets 里改 PRIVATE_KEY 即可，无需停服。
Q: KEY用完/失效会怎样？
A: 自动切换到下一个可用 KEY，全部 KEY 失效时返回 500，间隔自动重试。
Q: 能支持自定义 API 路径或白名单开放某些接口吗？
A: 可以，修改 check_private_key()，指定哪些路径不用或需要鉴权即可。
