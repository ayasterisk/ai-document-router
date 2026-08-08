"""Client gọi DeepSeek (OpenAI-compatible) — core model: deepseek-reasoner.

Hỗ trợ:
  - Model mặc định `deepseek-reasoner` (theo yêu cầu dự án).
  - Model mới của DeepSeek (deepseek-v4-pro/flash): bật thinking mode qua
    `thinking={"type": "enabled"}` (extra_body) — xem docs "Thinking Mode".
  - Có thể trỏ DEEPSEEK_BASE_URL sang endpoint OpenAI-compatible khác
    (vd LM Studio/vLLM serve deepseek-r1) để chạy hoàn toàn local.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from app.config import settings

# Model thuộc họ reasoning -> bật thinking mode, không set temperature/top_p
_REASONING_MODELS = {"deepseek-reasoner", "deepseek-r1", "deepseek-v4-pro"}


class DeepSeekClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ):
        self.api_key = (api_key or settings.DEEPSEEK_API_KEY).strip()
        self.base_url = base_url or settings.DEEPSEEK_BASE_URL
        self.model = model or settings.DEEPSEEK_MODEL
        self.timeout = timeout
        self._client: Optional[OpenAI] = None
        if self.api_key:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=timeout)

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def reasoning(self) -> bool:
        return self.model in _REASONING_MODELS

    # ------------------------------------------------------------------
    def chat(
        self,
        system: str,
        user: str,
        response_format: Optional[Dict[str, str]] = None,
        max_tokens: Optional[int] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Gọi chat completion.

        Trả (content, reasoning_content, error_message).
        - Tự thử JSON mode trước; nếu API từ chối (model cũ không hỗ trợ)
          thì gọi lại không response_format và trích JSON từ content.
        """
        if not self.available:
            return None, None, "Chưa cấu hình DEEPSEEK_API_KEY (xem .env.example)"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or settings.DEEPSEEK_MAX_TOKENS,
            "stream": False,
        }
        if self.reasoning:
            # deepseek-v4-*: bật thinking mode; deepseek-reasoner: mặc định suy luận
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        # 1) thử JSON mode (yêu cầu chuỗi "json" xuất hiện trong prompt)
        if response_format:
            try:
                return self._complete(kwargs, response_format)
            except Exception as e:
                # model cũ không hỗ trợ response_format -> thử lại không có
                if "response_format" in str(e).lower() or "invalid" in str(e).lower():
                    pass
                else:
                    return None, None, str(e)
        # 2) không JSON mode / fallback
        try:
            return self._complete(kwargs, None)
        except Exception as e:
            return None, None, str(e)

    def _complete(
        self, kwargs: Dict[str, Any], response_format: Optional[Dict[str, str]]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        assert self._client is not None
        params = dict(kwargs)
        if response_format:
            params["response_format"] = response_format
        resp = self._client.chat.completions.create(**params)
        message = resp.choices[0].message
        content = getattr(message, "content", None) or ""
        reasoning = getattr(message, "reasoning_content", None) or ""
        return content, reasoning, None


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Trích đối tượng JSON đầu tiên từ chuỗi (bỏ markdown fence nếu có)."""
    if not text:
        return None
    text = text.strip()
    # bỏ ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # tìm khối {...} lớn nhất
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


client = DeepSeekClient()
