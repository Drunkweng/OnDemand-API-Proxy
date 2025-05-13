import requests
import json
import base64
from typing import Dict, Optional
from flask import Flask, request, Response, stream_with_context
import os
import time
from datetime import datetime, timedelta

# Initialize Flask app
app = Flask(__name__)

# Load configuration from config.json if it exists, otherwise use environment variables
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        ACCOUNTS = config.get('accounts', [])
else:
    ACCOUNTS = []
    accounts_env = os.getenv("ONDEMAND_ACCOUNTS", "")
    if accounts_env:
        try:
            ACCOUNTS = json.loads(accounts_env).get('accounts', [])
        except json.JSONDecodeError:
            print("Error decoding ONDEMAND_ACCOUNTS environment variable. Using empty accounts list.")

if not ACCOUNTS:
    raise ValueError("No accounts found in config.json or environment variable ONDEMAND_ACCOUNTS.")

# Current account index (for round-robin selection)
current_account_index = 0

# In-memory storage for session and last interaction time per client
CLIENT_SESSIONS = {}  # Format: {client_id: {"session_id": str, "last_time": datetime, "user_id": str, "company_id": str, "token": str}}


class OnDemandAPIClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.token = ""
        self.refresh_token = ""
        self.user_id = ""
        self.company_id = ""
        self.session_id = ""
        self.base_url = "https://gateway.on-demand.io/v1"
        self.chat_base_url = "https://api.on-demand.io/chat/v1/client"

    def get_authorization(self) -> str:
        """Generate Basic Authorization header for login."""
        text = f"{self.email}:{self.password}"
        encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        return encoded

    def sign_in(self) -> bool:
        """Login to get token, refreshToken, userId, and companyId."""
        url = f"{self.base_url}/auth/user/signin"
        payload = {
            "accountType": "default"
        }
        headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
            'Accept': "application/json, text/plain, */*",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'Content-Type': "application/json",
            'Authorization': f"Basic {self.get_authorization()}",
            'Referer': "https://app.on-demand.io/"
        }

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            data = response.json()
            print("Raw response from sign_in:", json.dumps(data, indent=2))
            self.token = data.get('data', {}).get('tokenData', {}).get('token', '')
            self.refresh_token = data.get('data', {}).get('tokenData', {}).get('refreshToken', '')
            self.user_id = data.get('data', {}).get('user', {}).get('userId', '')
            self.company_id = data.get('data', {}).get('user', {}).get('default_company_id', '')
            print(f"Extracted Token: {self.token[:10]}... (truncated for security)")
            print(f"Extracted Refresh Token: {self.refresh_token[:10]}... (truncated for security)")
            print(f"Extracted User ID: {self.user_id}")
            print(f"Extracted Company ID: {self.company_id}")
            if self.token and self.user_id and self.company_id:
                print(f"Login successful for {self.email}. Token and user info retrieved.")
                return True
            else:
                print("Login successful but failed to extract required fields.")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Login failed for {self.email}: {e}")
            return False

    def refresh_token_if_needed(self) -> bool:
        """Refresh token if it is expired or invalid."""
        if not self.token or not self.refresh_token:
            print("No token or refresh token available. Please log in first.")
            return False

        url = f"{self.base_url}/auth/user/refresh_token"
        payload = {
            "data": {
                "token": self.token,
                "refreshToken": self.refresh_token
            }
        }
        headers = {
            'Content-Type': "application/json"
        }

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            data = response.json()
            print("Raw response from refresh_token:", json.dumps(data, indent=2))
            self.token = data.get('data', {}).get('token', '')
            self.refresh_token = data.get('data', {}).get('refreshToken', '')
            print(f"New Token: {self.token[:10]}... (truncated for security)")
            print("Token refreshed successfully.")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Token refresh failed: {e}")
            return False

    def create_session(self, external_user_id: str = "user-app-12345") -> Optional[str]:
        """Create a new session for chat."""
        if not self.token or not self.user_id or not self.company_id:
            print("No token or user info available. Please log in or refresh token.")
            return None

        url = f"{self.chat_base_url}/sessions"
        payload = {
            "externalUserId": external_user_id,
            "pluginIds": []
        }
        headers = {
            'Content-Type': "application/json",
            'Authorization': f"Bearer {self.token}",
            'x-company-id': self.company_id,
            'x-user-id': self.user_id
        }
        print(f"Creating session with company_id: {self.company_id}, user_id: {self.user_id}")

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            if response.status_code == 401:
                print("Token expired, refreshing...")
                if self.refresh_token_if_needed():
                    headers['Authorization'] = f"Bearer {self.token}"
                    response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            data = response.json()
            print("Raw response from create_session:", json.dumps(data, indent=2))
            self.session_id = data.get('data', {}).get('id', '')
            print(f"Session created successfully. Session ID: {self.session_id}")
            return self.session_id
        except requests.exceptions.RequestException as e:
            print(f"Session creation failed: {e}")
            return None

    def send_query(self, query: str, endpoint_id: str = "predefined-claude-3.7-sonnet", stream: bool = False) -> Dict:
        """Send a query to the chat session and handle streaming or non-streaming response."""
        if not self.session_id or not self.token:
            print("No session ID or token available. Please create a session first.")
            return {"error": "No session or token available"}

        url = f"{self.chat_base_url}/sessions/{self.session_id}/query"
        payload = {
            "endpointId": endpoint_id,
            "query": query,
            "pluginIds": [],
            "reasoningMode": "high",
            "responseMode": "stream" if stream else "sync",
            "debugMode": "on",
            "modelConfigs": {
                "fulfillmentPrompt": "",
                "stopTokens": [],
                "maxTokens": 0,
                "temperature": 0,
                "presencePenalty": 0,
                "frequencyPenalty": 0,
                "topP": 1
            },
            "fulfillmentOnly": False
        }
        headers = {
            'Content-Type': "application/json",
            'Authorization': f"Bearer {self.token}",
            'x-company-id': self.company_id
        }

        try:
            if stream:
                response = requests.post(url, data=json.dumps(payload), headers=headers, stream=True)
                if response.status_code == 401:
                    print("Token expired, refreshing...")
                    if self.refresh_token_if_needed():
                        headers['Authorization'] = f"Bearer {self.token}"
                        response = requests.post(url, data=json.dumps(payload), headers=headers, stream=True)
                response.raise_for_status()
                return {"stream": True, "response": response}
            else:
                response = requests.post(url, data=json.dumps(payload), headers=headers)
                if response.status_code == 401:
                    print("Token expired, refreshing...")
                    if self.refresh_token_if_needed():
                        headers['Authorization'] = f"Bearer {self.token}"
                        response = requests.post(url, data=json.dumps(payload), headers=headers)
                response.raise_for_status()
                full_answer = ""
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data:"):
                            json_str = decoded_line[len("data:"):]
                            if json_str == "[DONE]":
                                break
                            try:
                                event_data = json.loads(json_str)
                                if event_data.get("eventType", "") == "fulfillment":
                                    full_answer += event_data.get("answer", "")
                            except json.JSONDecodeError:
                                continue
                return {"stream": False, "content": full_answer}
        except requests.exceptions.RequestException as e:
            print(f"Query failed: {e}")
            return {"error": str(e)}


# Initialize the first client with the first account
def get_next_client():
    global current_account_index
    account = ACCOUNTS[current_account_index]
    email = account.get('email')
    password = account.get('password')
    print(f"Using account: {email}")
    current_account_index = (current_account_index + 1) % len(ACCOUNTS)  # Round-robin to next account
    return OnDemandAPIClient(email, password)


# Current client (will be replaced when switching accounts)
current_client = get_next_client()

# Global variable to track initialization
initialized = False


@app.before_request
def initialize_client():
    global initialized, current_client
    if not initialized:
        if current_client.sign_in():
            current_client.create_session()
            initialized = True
        else:
            print("Initialization failed. Switching to next account.")
            current_client = get_next_client()
            initialize_client()  # Recursive call with new client


@app.route('/v1/models', methods=['GET'])
def get_models():
    """Return a list of available models in OpenAI format."""
    models_response = {
        "object": "list",
        "data": [
            {
                "id": "gpto3-mini",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "gpt-4o",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "gpt-4.1",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "gpt-4.1-mini",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "gpt-4.1-nano",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "gpt-4o-mini",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "deepseek-v3",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "deepseek-r1",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "claude-3.7-sonnet",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            },
            {
                "id": "gemini-2.0-flash",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "on-demand.io"
            }
        ]
    }
    return models_response


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    global current_client
    data = request.get_json()
    print("Received OpenAI request:", json.dumps(data, indent=2))

    # Extract client ID (use IP address as a simple identifier for different clients)
    client_id = request.remote_addr  # Alternatively, use a unique ID from request if provided by Cherry Studio

    # Check last interaction time for this client
    current_time = datetime.now()
    if client_id in CLIENT_SESSIONS:
        last_time = CLIENT_SESSIONS[client_id].get("last_time")
        if last_time and current_time - last_time > timedelta(minutes=10):
            print(f"Client {client_id} inactive for over 10 minutes. Switching session or account.")
            # Option 1: Create new session with current account
            new_session = current_client.create_session()
            if new_session:
                CLIENT_SESSIONS[client_id]["session_id"] = new_session
                print(f"New session created for client {client_id}: {new_session}")
            else:
                # Option 2: If session creation fails, switch account
                print("Failed to create new session. Switching to next account.")
                current_client = get_next_client()
                if current_client.sign_in():
                    new_session = current_client.create_session()
                    if new_session:
                        CLIENT_SESSIONS[client_id] = {
                            "session_id": new_session,
                            "last_time": current_time,
                            "user_id": current_client.user_id,
                            "company_id": current_client.company_id,
                            "token": current_client.token
                        }
                        print(f"Switched account and created new session for client {client_id}: {new_session}")
                    else:
                        return {"error": "Failed to create session with new account"}, 500
                else:
                    return {"error": "Failed to login with new account"}, 500
    else:
        # New client, use current session or create one
        if not current_client.session_id:
            if not current_client.sign_in() or not current_client.create_session():
                return {"error": "Failed to initialize client session"}, 500
        CLIENT_SESSIONS[client_id] = {
            "session_id": current_client.session_id,
            "last_time": current_time,
            "user_id": current_client.user_id,
            "company_id": current_client.company_id,
            "token": current_client.token
        }

    # Update last interaction time
    CLIENT_SESSIONS[client_id]["last_time"] = current_time

    # Extract parameters from OpenAI request
    messages = data.get('messages', [])
    stream = data.get('stream', False)
    model = data.get('model', 'claude-3.7-sonnet')

    if not messages:
        return {"error": "No messages found in request"}, 400

    # Extract only the latest user message as the query (rely on session_id for context)
    latest_user_query = ""
    for msg in reversed(messages):
        if msg.get('role', '') == 'user':
            latest_user_query = msg.get('content', '')
            break
    if not latest_user_query:
        return {"error": "No user message found in request"}, 400

    # Add explicit instruction to reply in Chinese and be direct
    query = f"请用英文思考,用中文回答以下问题，不要提及上下文或推理过程：{latest_user_query}"
    print(f"Constructed Query for on-demand.io (relying on session_id for context, with Chinese instruction): {query}")

    # Map the model ID to on-demand.io endpoint ID
    model_mapping = {
        "gpto3-mini": "predefined-openai-gpto3-mini",
        "gpt-4o": "predefined-openai-gpt4o",
        "gpt-4.1": "predefined-openai-gpt4.1",
        "gpt-4.1-mini": "predefined-openai-gpt4.1-mini",
        "gpt-4.1-nano": "predefined-openai-gpt4.1-nano",
        "gpt-4o-mini": "predefined-openai-gpt4o-mini",
        "deepseek-v3": "predefined-deepseek-v3",
        "deepseek-r1": "predefined-deepseek-r1",
        "claude-3.7-sonnet": "predefined-claude-3.7-sonnet",
        "gemini-2.0-flash": "predefined-gemini-2.0-flash"
    }
    endpoint_id = model_mapping.get(model, "predefined-claude-3.7-sonnet")  # Default to Claude if model not found

    # Send query to OnDemand API
    result = current_client.send_query(query, endpoint_id=endpoint_id, stream=stream)

    if "error" in result:
        return {"error": result["error"]}, 500

    if stream:
        def generate_stream():
            for line in result["response"].iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data:"):
                        json_str = decoded_line[len("data:"):]
                        if json_str == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            event_data = json.loads(json_str)
                            if event_data.get("eventType", "") == "fulfillment":
                                content = event_data.get("answer", "")
                                stream_response = {
                                    "id": f"chatcmpl-{int(time.time())}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model,
                                    "choices": [
                                        {
                                            "delta": {"content": content},
                                            "index": 0,
                                            "finish_reason": None
                                        }
                                    ]
                                }
                                yield f"data: {json.dumps(stream_response)}\n\n"
                        except json.JSONDecodeError:
                            continue

        return Response(stream_with_context(generate_stream()), content_type='text/event-stream')
    else:
        response = {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": result["content"]
                    },
                    "finish_reason": "stop",
                    "index": 0
                }
            ],
            "usage": {
                "prompt_tokens": 0,  # Placeholder, can be updated if metrics are available
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        return response


if __name__ == "__main__":
    # Get port from environment variable (Hugging Face Spaces uses PORT env var)
    port = int(os.getenv("PORT", 7860))
    print(f"Starting Flask app on port {port}")
    # Run the Flask app with host 0.0.0.0 to be accessible in Docker
    app.run(host='0.0.0.0', port=port, debug=False)
