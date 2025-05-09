from flask import Flask, request, Response, jsonify
import requests
import uuid
import time
import json
import threading
import logging
import os

# ====== 读取 Huggingface Secret 配置的私有key =======
PRIVATE_KEY = os.environ.get("PRIVATE_KEY", "114514")
SAFE_HEADER = "X-API-KEY"

# 全局接口访问权限检查
def check_private_key():
    if request.path in ["/", "/favicon.ico"]:
        return
    key = request.headers.get(SAFE_HEADER)
    if not key or key != PRIVATE_KEY:
        return jsonify({"error": "Unauthorized, must provide correct X-API-KEY"}), 401

# 应用所有API鉴权
app = Flask(__name__)
app.before_request(check_private_key)

# ========== KEY池（每行一个）==========
ONDEMAND_APIKEYS = [
    "KEY1",
    "KEY2",
]
BAD_KEY_RETRY_INTERVAL = 600  # 秒
SESSION_TIMEOUT = 600  # 对话超时时间（10分钟）

# ========== OnDemand模型映射 ==========
MODEL_MAP = {
    "gpto3-mini": "predefined-openai-gpto3-mini",
    "gpt-4o": "predefined-openai-gpt4o",
    "gpt-4.1": "predefined-openai-gpt4.1",
    "gpt-4.1-mini": "predefined-openai-gpt4.1-mini",
    "gpt-4.1-nano": "predefined-openai-gpt4.1-nano",
    "gpt-4o-mini": "predefined-openai-gpt4o-mini",
    "deepseek-v3": "predefined-deepseek-v3",
    "deepseek-r1": "predefined-deepseek-r1",
    "claude-3.7-sonnet": "predefined-claude-3.7-sonnet",
    "gemini-2.0-flash": "predefined-gemini-2.0-flash",
}
DEFAULT_ONDEMAND_MODEL = "predefined-openai-gpt4o"
# ==========================================

class KeyManager:
    def __init__(self, key_list):
        self.key_list = list(key_list)
        self.lock = threading.Lock()
        self.key_status = {k: {"bad": False, "bad_ts": None} for k in self.key_list}
        self.idx = 0
        # 新增：当前正在使用的key和session
        self.current_key = None
        self.current_session = None
        self.last_used_time = None

    def display_key(self, key):
        return f"{key[:6]}...{key[-4:]}"

    def get(self):
        with self.lock:
            now = time.time()
            # 检查对话是否超时
            if self.current_key and self.last_used_time and (now - self.last_used_time > SESSION_TIMEOUT):
                print(f"【对话超时】上次使用时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_used_time))}")
                print(f"【对话超时】当前时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}")
                print(f"【对话超时】超时{SESSION_TIMEOUT//60}分钟，切换新会话")
                self.current_key = None
                self.current_session = None

            # 如果已有正在使用的key，继续使用
            if self.current_key:
                if not self.key_status[self.current_key]["bad"]:
                    print(f"【对话请求】【继续使用API KEY: {self.display_key(self.current_key)}】【状态：正常】")
                    self.last_used_time = now
                    return self.current_key
                else:
                    # 当前key已标记为异常，需要切换
                    self.current_key = None
                    self.current_session = None

            # 如果没有当前key或当前key无效，选择新的key
            total = len(self.key_list)
            for _ in range(total):
                key = self.key_list[self.idx]
                self.idx = (self.idx + 1) % total
                s = self.key_status[key]
                if not s["bad"]:
                    print(f"【对话请求】【使用新API KEY: {self.display_key(key)}】【状态：正常】")
                    self.current_key = key
                    self.current_session = None  # 强制创建新会话
                    self.last_used_time = now
                    return key
                if s["bad"] and s["bad_ts"]:
                    ago = now - s["bad_ts"]
                    if ago >= BAD_KEY_RETRY_INTERVAL:
                        print(f"【KEY自动尝试恢复】API KEY: {self.display_key(key)} 满足重试周期，标记为正常")
                        self.key_status[key]["bad"] = False
                        self.key_status[key]["bad_ts"] = None
                        self.current_key = key
                        self.current_session = None  # 强制创建新会话
                        self.last_used_time = now
                        return key
            
            print("【警告】全部KEY已被禁用，强制选用第一个KEY继续尝试:", self.display_key(self.key_list[0]))
            for k in self.key_list:
                self.key_status[k]["bad"] = False
                self.key_status[k]["bad_ts"] = None
            self.idx = 0
            self.current_key = self.key_list[0]
            self.current_session = None  # 强制创建新会话
            self.last_used_time = now
            print(f"【对话请求】【使用API KEY: {self.display_key(self.current_key)}】【状态：强制尝试（全部异常）】")
            return self.current_key

    def mark_bad(self, key):
        with self.lock:
            if key in self.key_status and not self.key_status[key]["bad"]:
                print(f"【禁用KEY】API KEY: {self.display_key(key)}，接口返回无效（将在{BAD_KEY_RETRY_INTERVAL//60}分钟后自动重试）")
                self.key_status[key]["bad"] = True
                self.key_status[key]["bad_ts"] = time.time()
                if self.current_key == key:
                    self.current_key = None
                    self.current_session = None

    def get_session(self, apikey):
        with self.lock:
            if not self.current_session:
                try:
                    self.current_session = create_session(apikey)
                    print(f"【创建新会话】SESSION ID: {self.current_session}")
                except Exception as e:
                    print(f"【创建会话失败】错误: {str(e)}")
                    raise
            self.last_used_time = time.time()
            return self.current_session

keymgr = KeyManager(ONDEMAND_APIKEYS)

ONDEMAND_API_BASE = "https://api.on-demand.io/chat/v1"

def get_endpoint_id(openai_model):
    m = str(openai_model or "").lower().replace(" ", "")
    return MODEL_MAP.get(m, DEFAULT_ONDEMAND_MODEL)

def create_session(apikey, external_user_id=None, plugin_ids=None):
    url = f"{ONDEMAND_API_BASE}/sessions"
    payload = {"externalUserId": external_user_id or str(uuid.uuid4())}
    if plugin_ids is not None:
        payload["pluginIds"] = plugin_ids
    headers = {"apikey": apikey, "Content-Type": "application/json"}
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()["data"]["id"]

def format_openai_sse_delta(chunk_str):
    return f"data: {json.dumps(chunk_str, ensure_ascii=False)}\n\n"

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    data = request.json
    if not data or "messages" not in data:
        return jsonify({"error": "请求缺少messages字段"}), 400

    messages = data["messages"]
    openai_model = data.get("model", "gpt-4o")
    endpoint_id = get_endpoint_id(openai_model)
    is_stream = bool(data.get("stream", False))

    user_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_msg = msg.get("content")
            break
    if user_msg is None:
        return jsonify({"error": "未找到用户消息"}), 400

    def with_valid_key(func):
        bad_cnt = 0
        max_retry = len(keymgr.key_list)*2
        while bad_cnt < max_retry:
            key = keymgr.get()
            try:
                return func(key)
            except Exception as e:
                if hasattr(e, 'response'):
                    r = e.response
                    if r.status_code in (401, 403, 429, 500):
                        keymgr.mark_bad(key)
                        bad_cnt += 1
                        continue
                raise
        return jsonify({"error": "没有可用API KEY，请补充新KEY或联系技术支持"}), 500

    if is_stream:
        def generate():
            def do_once(apikey):
                # 使用KeyManager获取或创建session
                sid = keymgr.get_session(apikey)
                url = f"{ONDEMAND_API_BASE}/sessions/{sid}/query"
                payload = {
                    "query": user_msg,
                    "endpointId": endpoint_id,
                    "pluginIds": [],
                    "responseMode": "stream"
                }
                headers = {"apikey": apikey, "Content-Type": "application/json", "Accept": "text/event-stream"}
                with requests.post(url, json=payload, headers=headers, stream=True, timeout=120) as resp:
                    if resp.status_code != 200:
                        raise requests.HTTPError(response=resp)
                    answer_acc = ""
                    first_chunk = True
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        line = line.decode("utf-8")
                        if line.startswith("data:"):
                            datapart = line[5:].strip()
                            if datapart == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            elif datapart.startswith("[ERROR]:"):
                                err_json = datapart[len("[ERROR]:"):].strip()
                                yield format_openai_sse_delta({"error": err_json})
                                break
                            else:
                                try:
                                    js = json.loads(datapart)
                                except Exception:
                                    continue
                                if js.get("eventType") == "fulfillment":
                                    delta = js.get("answer", "")
                                    answer_acc += delta
                                    chunk = {
                                        "id": "chatcmpl-" + str(uuid.uuid4())[:8],
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": openai_model,
                                        "choices": [{
                                            "delta": {
                                                "role": "assistant",
                                                "content": delta
                                            } if first_chunk else {
                                                "content": delta
                                            },
                                            "index": 0,
                                            "finish_reason": None
                                        }]
                                    }
                                    yield format_openai_sse_delta(chunk)
                                    first_chunk = False
                    yield "data: [DONE]\n\n"
            yield from with_valid_key(do_once)
        return Response(generate(), content_type='text/event-stream')

    def nonstream(apikey):
        # 使用KeyManager获取或创建session
        sid = keymgr.get_session(apikey)
        url = f"{ONDEMAND_API_BASE}/sessions/{sid}/query"
        payload = {
            "query": user_msg,
            "endpointId": endpoint_id,
            "pluginIds": [],
            "responseMode": "sync"
        }
        headers = {"apikey": apikey, "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        if resp.status_code != 200:
            raise requests.HTTPError(response=resp)
        ai_response = resp.json()["data"]["answer"]
        resp_obj = {
            "id": "chatcmpl-" + str(uuid.uuid4())[:8],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": openai_model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ai_response},
                    "finish_reason": "stop"
                }
            ],
            "usage": {}
        }
        return jsonify(resp_obj)

    return with_valid_key(nonstream)

@app.route("/v1/models", methods=["GET"])
def models():
    model_objs = []
    for mdl in MODEL_MAP.keys():
        model_objs.append({
            "id": mdl,
            "object": "model",
            "owned_by": "ondemand-proxy"
        })
    uniq = {m["id"]: m for m in model_objs}.values()
    return jsonify({
        "object": "list",
        "data": list(uniq)
    })

if __name__ == "__main__":
    log_fmt = '[%(asctime)s] %(levelname)s: %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt)
    print("======== OnDemand KEY池数量：", len(ONDEMAND_APIKEYS), "========")
    app.run(host="0.0.0.0", port=7860, debug=False)
