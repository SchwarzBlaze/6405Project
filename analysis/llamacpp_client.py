"""HTTP client for a local llama.cpp OpenAI-compatible server."""

from __future__ import annotations

import base64
import json
import mimetypes
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app_i18n import normalize_ui_language


class LlamaCppServerClient:
    """Small wrapper around llama-server's chat-completions endpoint."""

    def __init__(self, server_url: str, timeout_seconds: int = 120, ui_language: str = "zh"):
        self.endpoint = self._normalize_endpoint(server_url)
        self.timeout_seconds = timeout_seconds
        self.ui_language = normalize_ui_language(ui_language)

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
            if _looks_like_memory_error(detail):
                raise RuntimeError(self._memory_error_message(exc.code, detail)) from exc
            raise RuntimeError(self._http_error_message(exc.code, detail)) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(self._timeout_message()) from exc
        except URLError as exc:
            raise RuntimeError(self._connection_message()) from exc

        if status_code >= 400:
            if _looks_like_memory_error(response_text):
                raise RuntimeError(self._memory_error_message(status_code, response_text))
            raise RuntimeError(self._http_error_message(status_code, response_text))

        try:
            payload = json.loads(response_text)
        except ValueError as exc:
            raise RuntimeError(self._invalid_response_message(response_text)) from exc

        try:
            message = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(self._bad_shape_message(payload)) from exc

        reasoning_content = None
        try:
            reasoning_content = payload["choices"][0]["message"].get("reasoning_content")
        except Exception:
            reasoning_content = None

        if (message == "" or message == [] or message is None) and reasoning_content:
            raise RuntimeError(self._reasoning_only_message())

        if isinstance(message, list):
            text_parts = []
            for part in message:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(str(part.get("text", "")))
            return "\n".join(part for part in text_parts if part.strip()).strip()

        return str(message).strip()

    def _memory_error_message(self, status_code: int, detail: str) -> str:
        if self.ui_language == "en":
            return (
                "The AI service failed during inference, possibly because GPU or system memory is insufficient.\n"
                f"Endpoint: {self.endpoint}\n"
                f"HTTP {status_code}\n"
                f"Details: {_safe_response_text(detail)}"
            )
        return (
            "AI 服务推理失败，可能是显存或内存不足。\n"
            f"地址: {self.endpoint}\n"
            f"HTTP {status_code}\n"
            f"详情: {_safe_response_text(detail)}"
        )

    def _http_error_message(self, status_code: int, detail: str) -> str:
        if self.ui_language == "en":
            return (
                "The AI service returned an error response.\n"
                f"Endpoint: {self.endpoint}\n"
                f"HTTP {status_code}\n"
                f"Details: {_safe_response_text(detail)}"
            )
        return (
            "AI 服务返回了错误响应。\n"
            f"地址: {self.endpoint}\n"
            f"HTTP {status_code}\n"
            f"详情: {_safe_response_text(detail)}"
        )

    def _timeout_message(self) -> str:
        if self.ui_language == "en":
            return (
                "The AI service timed out.\n"
                f"Endpoint: {self.endpoint}\n"
                "Please try again later or reduce the input image size."
            )
        return (
            "AI 服务响应超时。\n"
            f"地址: {self.endpoint}\n"
            "请稍后重试，或减小输入图片尺寸。"
        )

    def _connection_message(self) -> str:
        if self.ui_language == "en":
            return (
                "Could not connect to the AI service.\n"
                f"Current endpoint: {self.endpoint}\n\n"
                "Please start the local AI service first, for example:\n"
                "  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off"
            )
        return (
            "无法连接到 AI 服务。\n"
            f"当前地址: {self.endpoint}\n\n"
            "请先启动本地 AI 服务，例如：\n"
            "  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off"
        )

    def _invalid_response_message(self, response_text: str) -> str:
        if self.ui_language == "en":
            return (
                "The AI service returned content that could not be parsed.\n"
                f"Endpoint: {self.endpoint}\n"
                f"Response preview: {_safe_response_text(response_text)}"
            )
        return (
            "AI 服务返回的内容无法识别。\n"
            f"地址: {self.endpoint}\n"
            f"响应片段: {_safe_response_text(response_text)}"
        )

    def _bad_shape_message(self, payload: object) -> str:
        if self.ui_language == "en":
            return f"The AI service returned an unexpected response shape: {payload}"
        return f"AI 服务响应格式异常: {payload}"

    def _reasoning_only_message(self) -> str:
        if self.ui_language == "en":
            return (
                "The AI service is still in reasoning mode and has not returned the final answer yet.\n"
                "Restart the service like this and try again:\n"
                "  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off\n"
                "If you still want thinking enabled, at least add:\n"
                "  --reasoning-budget 0"
            )
        return (
            "AI 服务当前停在思考阶段，还没有返回正式答案。\n"
            "请按下面的方式重新启动服务后再试：\n"
            "  llama-server -hf ggml-org/gemma-4-E2B-it-GGUF --reasoning off\n"
            "如果你仍想保留 thinking，也至少加上：\n"
            "  --reasoning-budget 0"
        )

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


def _looks_like_memory_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        key in lowered
        for key in [
            "out of memory",
            "cuda error",
            "cuda out of memory",
            "insufficient memory",
            "failed to allocate",
            "memory allocation",
            "vram",
        ]
    )
