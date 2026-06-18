import json
import os
import re
import warnings
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


def _fix_json_string(raw: str) -> str:
    """Fix common illegal JSON strings so json.loads can parse them."""
    s = raw.strip()
    if not s.startswith("{"):
        return s
    # 1. Remove trailing commas before } or ]
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # 2. Replace single quotes with double quotes (outside strings)
    def _fix_quotes(text):
        result = []
        in_string = False
        escape_next = False
        i = 0
        while i < len(text):
            ch = text[i]
            if escape_next:
                result.append(ch)
                escape_next = False
                i += 1
                continue
            if ch == "\\":
                result.append(ch)
                escape_next = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                i += 1
                continue
            if not in_string and ch == "'":
                result.append('"')
                i += 1
                continue
            result.append(ch)
            i += 1
        return "".join(result)
    s = _fix_quotes(s)
    # 3. Quote unquoted keys
    s = re.sub(r"(?<=[{,])\s*(\w+)\s*:", r' "\1":', s)
    return s


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI wrapper that normalizes typed content blocks to text,
    and auto-repairs illegal JSON arguments from LLM responses."""

    def invoke(self, input, config=None, **kwargs):
        try:
            result = super().invoke(input, config, **kwargs)
        except Exception as exc:
            err_msg = str(exc).lower()
            if any(kw in err_msg for kw in [
                "expecting property name", "double quotes", "jsondecodeerror",
                "char 1", "bad request", "400",
            ]):
                warnings.warn(
                    f"[LLM] Detected illegal JSON arguments, attempting auto-repair: {exc}",
                    UserWarning,
                    stacklevel=2,
                )
                import httpx
                original_client = kwargs.get("http_client") or self.http_client
                if original_client and hasattr(original_client, "transport"):
                    class RepairTransport(httpx.BaseTransport):
                        def __init__(self, orig):
                            self.orig = orig
                        def handle_request(self, request):
                            response = self.orig.handle_request(request)
                            url = str(request.url)
                            if "chat" in url and "completions" in url:
                                try:
                                    body = response.read()
                                    data = json.loads(body)
                                    if isinstance(data, dict) and "choices" in data:
                                        for choice in data["choices"]:
                                            msg = choice.get("message", {})
                                            if isinstance(msg, dict) and "tool_calls" in msg:
                                                for tc in msg["tool_calls"]:
                                                    func = tc.get("function", {})
                                                    if isinstance(func, dict) and "arguments" in func:
                                                        raw_args = func["arguments"]
                                                        if isinstance(raw_args, str):
                                                            try:
                                                                json.loads(raw_args)
                                                            except (json.JSONDecodeError, ValueError):
                                                                fixed = _fix_json_string(raw_args)
                                                                try:
                                                                    json.loads(fixed)
                                                                    func["arguments"] = fixed
                                                                except (json.JSONDecodeError, ValueError):
                                                                    func["arguments"] = "{}"
                                    repaired_body = json.dumps(data, ensure_ascii=False)
                                    response._content = repaired_body.encode()
                                except Exception:
                                    pass
                            return response
                    repair_client = httpx.Client(transport=RepairTransport(original_client.transport))
                    kwargs["http_client"] = repair_client
                    try:
                        result = super().invoke(input, config, **kwargs)
                        return normalize_content(result)
                    except Exception:
                        pass
            raise
        return normalize_content(result)


_PASSTHROUGH_KWARGS = (
    "temperature",
    "max_tokens",
    "timeout",
    "max_retries",
    "callbacks",
    "http_client",
    "http_async_client",
)

_PROVIDER_CONFIG = {
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4/", "ZHIPU_API_KEY"),
    "qianfan": ("https://qianfan.baidubce.com/v2", "QIANFAN_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "aihubmix": ("https://aihubmix.com/v1", "AIHUBMIX_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "custom_openai": (None, "CUSTOM_OPENAI_API_KEY"),
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI and OpenAI-compatible providers."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.provider in _PROVIDER_CONFIG:
            default_base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = self.base_url or default_base_url
            if api_key_env:
                api_key = self.kwargs.get("api_key") or os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url
            api_key = self.kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
