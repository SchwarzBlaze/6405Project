"""Model loading and inference utilities for Gemma 4."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import textwrap
from pathlib import Path
from typing import Any

from analysis.llamacpp_client import LlamaCppServerClient

logger = logging.getLogger(__name__)

MODEL_REGISTRY = {
    "e2b": "google/gemma-4-E2B-it",
    "e4b": "google/gemma-4-E4B-it",
}

_LOCAL_DIR_PATTERNS = [
    "./gemma4_{name}_model",
    "./gemma4-{name}-model",
    "./gemma4_{name}",
]


def _find_local_model(model_name: str) -> str | None:
    for pattern in _LOCAL_DIR_PATTERNS:
        path = pattern.format(name=model_name)
        if os.path.isdir(path):
            return path
    return None


def load_model(
    model_name: str = "e2b",
    local_dir: str | None = None,
    server_url: str | None = None,
):
    """Load a Gemma 4 model for local HF inference or llama.cpp server."""
    if server_url:
        client = LlamaCppServerClient(server_url)
        logger.info("Using llama.cpp server at %s", client.endpoint)
        return client, None

    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    if local_dir and os.path.isdir(local_dir):
        model_path = local_dir
    else:
        local = _find_local_model(model_name)
        model_path = local if local else MODEL_REGISTRY.get(model_name, model_name)

    logger.info("Loading model from %s ...", model_path)

    if not torch.cuda.is_available():
        logger.warning(
            "CUDA is not available in the current PyTorch environment. "
            "Gemma 4 can still try to load, but performance may be unusably slow."
        )

    load_kwargs: dict[str, Any] = {
        "torch_dtype": torch.bfloat16,
        "attn_implementation": "sdpa",
        "low_cpu_mem_usage": True,
    }
    if torch.cuda.is_available():
        load_kwargs["device_map"] = {"": 0}
    else:
        load_kwargs["device_map"] = "auto"

    try:
        model = AutoModelForMultimodalLM.from_pretrained(
            model_path,
            **load_kwargs,
        )
        processor = AutoProcessor.from_pretrained(model_path, padding_side="left")
    except Exception as exc:
        if _is_windows_pagefile_error(exc):
            raise RuntimeError(_format_pagefile_error(model_path, exc, torch.cuda.is_available())) from exc
        if os.path.isdir(model_path):
            raise
        raise RuntimeError(_format_remote_load_error(model_path, exc)) from exc

    logger.info("Model loaded on %s", model.device)
    return model, processor


def generate(model, processor, messages: list[dict], max_tokens: int = 1024) -> str:
    """Run a single chat-completion turn and return the generated text."""
    if isinstance(model, LlamaCppServerClient):
        converted = _convert_messages_for_llamacpp(messages)
        return model.generate(converted, max_tokens=max_tokens)

    import torch

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        add_generation_prompt=True,
    ).to(model.device)

    input_len = inputs["input_ids"].shape[-1]

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,
            cache_implementation="static",
        )

    generated_ids = output[0][input_len:]
    text = processor.decode(generated_ids, skip_special_tokens=True)

    try:
        result = processor.parse_response(text)
        return result.get("content", text.strip())
    except Exception:
        return text.strip()


def _convert_messages_for_llamacpp(messages: list[dict]) -> list[dict]:
    converted: list[dict] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = message.get("content")

        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            converted.append({"role": role, "content": str(content or "")})
            continue

        items: list[dict] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                items.append({"type": "text", "text": str(item.get("text", ""))})
            elif item_type == "image":
                image_path = item.get("url")
                if image_path:
                    items.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": _image_path_to_data_uri(str(image_path))},
                        }
                    )
            elif item_type == "image_url":
                items.append(item)

        converted.append({"role": role, "content": items})

    return converted


def _image_path_to_data_uri(image_path: str) -> str:
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{data}"


def _format_remote_load_error(model_path: str, exc: Exception) -> str:
    return textwrap.dedent(
        f"""
        Failed to load remote model "{model_path}" from Hugging Face.

        The original error was:
          {type(exc).__name__}: {exc}

        Common fixes:
        1. Make sure you have accepted the Gemma license on Hugging Face for this model.
        2. Log in before running:
             hf auth login
        3. If downloads are unstable on your network, disable hf-xet before Python starts:
             $env:HF_HUB_DISABLE_XET="1"
        4. Pre-download the model into a local folder and run with --local-model-dir:
             hf download {model_path} --local-dir .\\gemma4_e2b_model
        """
    ).strip()


def _is_windows_pagefile_error(exc: Exception) -> bool:
    text = str(exc)
    return "1455" in text or "页面文件太小" in text


def _format_pagefile_error(model_path: str, exc: Exception, cuda_available: bool) -> str:
    cuda_line = (
        "Current PyTorch can use CUDA."
        if cuda_available
        else "Current PyTorch is CPU-only, so the model is loading into system RAM/virtual memory."
    )
    return textwrap.dedent(
        f"""
        Failed to load model "{model_path}" because Windows reported:
          {type(exc).__name__}: {exc}

        This usually means the model is too large for the current RAM + page file setup.
        {cuda_line}

        Recommended fixes:
        1. Use llama.cpp server instead of native Transformers on Windows.
        2. Install a CUDA-enabled PyTorch build if you still need local loading.
        3. Increase the Windows page file size, then restart Python.
        4. Close memory-heavy applications before launching the app.
        """
    ).strip()
