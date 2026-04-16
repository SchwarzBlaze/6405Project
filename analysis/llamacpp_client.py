"""HTTP client for a local llama.cpp OpenAI-compatible server."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class LlamaCppServerClient:
    """Small wrapper around llama-server's chat-completions endpoint."""

    def __init__(self, server_url: str, timeout_seconds: int = 120):
        self.endpoint = self._normalize_endpoint(server_url)
        self.timeout_seconds = timeout_seconds

    def generate(self, messages: list[dict], max_tokens: int = 384) -> str:
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "stream": False,
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                status_code = response.status
                response_text = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                "llama.cpp 服务返回了错误响应。\n"
                f"地址: {self.endpoint}\n"
                f"HTTP {exc.code}\n"
                f"详情: {_safe_response_text(detail)}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                "无法连接到 llama.cpp 服务。\n"
                f"当前地址: {self.endpoint}\n\n"
                "请先启动本地服务，例如:\n"
                "  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF\n"
                "然后再启动桌面学习模式。"
            ) from exc

        if status_code >= 400:
            raise RuntimeError(
                "llama.cpp 服务返回了错误响应。\n"
                f"地址: {self.endpoint}\n"
                f"HTTP {status_code}\n"
                f"详情: {_safe_response_text(response_text)}"
            )

        try:
            payload = json.loads(response_text)
        except ValueError as exc:
            raise RuntimeError(
                "llama.cpp 服务返回的不是合法 JSON。\n"
                f"地址: {self.endpoint}\n"
                f"响应片段: {_safe_response_text(response_text)}"
            ) from exc

        try:
            message = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"llama.cpp 响应格式异常: {payload}") from exc

        reasoning_content = None
        try:
            reasoning_content = payload["choices"][0]["message"].get("reasoning_content")
        except Exception:
            reasoning_content = None

        if (message == "" or message == [] or message is None) and reasoning_content:
            raise RuntimeError(
                "llama.cpp 当前把结果停在了 thinking 阶段，未返回正式答案。\n"
                "请用下面的方式重新启动服务后再试：\n"
                "  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off\n"
                "如果你仍想保留 thinking，也至少加上：\n"
                "  --reasoning-budget 0"
            )

        if isinstance(message, list):
            text_parts = []
            for part in message:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
            return "\n".join(part for part in text_parts if part.strip()).strip()

        return str(message).strip()

    @staticmethod
    def build_multimodal_message(prompt: str, image_path: str) -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _image_path_to_data_uri(image_path),
                    },
                },
            ],
        }

    @staticmethod
    def _normalize_endpoint(server_url: str) -> str:
        text = server_url.strip()
        if not text:
            text = "http://127.0.0.1:8080"

        if not text.startswith(("http://", "https://")):
            text = f"http://{text}"

        parsed = urlparse(text)
        path = parsed.path.rstrip("/")

        if path.endswith("/v1/chat/completions"):
            final_path = path
        elif path.endswith("/v1"):
            final_path = f"{path}/chat/completions"
        elif path:
            final_path = f"{path}/v1/chat/completions"
        else:
            final_path = "/v1/chat/completions"

        return parsed._replace(path=final_path, params="", query="", fragment="").geturl()


def _image_path_to_data_uri(image_path: str) -> str:
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _safe_response_text(text: str) -> str:
    text = text.strip()
    if len(text) > 500:
        return text[:500] + "..."
    return text
