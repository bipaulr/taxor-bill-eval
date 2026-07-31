"""
OpenRouter free-tier extractors (OpenAI-compatible gateway).

Free vision models available July 2026 (subject to rotation):
  - google/gemma-4-31b-it:free      Gemma 4 31B, multilingual (140+ langs)
  - nvidia/nemotron-nano-12b-v2-vl:free  NVidia 12B vision-language
Rate limits on :free models: ~20 req/min, ~200 req/day (per model).
"""

from typing import Any
import base64

from openai import OpenAI

from src.config import settings
from src.extractor import BaseExtractor, EXTRACTION_PROMPT, register_extractor


class OpenRouterExtractor(BaseExtractor):
    """Generic extractor talking to OpenRouter's OpenAI-compatible API."""

    # OpenRouter reports $0 pricing for :free models; token cost is 0.
    input_price_per_1m = 0.0
    output_price_per_1m = 0.0

    def __init__(self):
        if not settings.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Get a free key at "
                "https://openrouter.ai/settings/keys and add it to .env"
            )
        self.client = OpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/bipaulr/taxor",
                "X-Title": "BillEval",
            },
        )

    def _extract_impl(self, image_path: str) -> dict[str, Any]:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64}"

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1024,
            temperature=0.1,
        )

        self._last_input_tokens = response.usage.prompt_tokens if response.usage else 0
        self._last_output_tokens = response.usage.completion_tokens if response.usage else 0

        import json
        parsed = json.loads(response.choices[0].message.content)
        parsed["_model"] = self.model_name
        parsed["_input_tokens"] = self._last_input_tokens
        parsed["_output_tokens"] = self._last_output_tokens
        return parsed

    def last_cost(self) -> float:
        input_cost = (self._last_input_tokens / 1_000_000) * self.input_price_per_1m
        output_cost = (self._last_output_tokens / 1_000_000) * self.output_price_per_1m
        return round(input_cost + output_cost, 8)


@register_extractor("gemma-4-31b")
class Gemma31BExtractor(OpenRouterExtractor):
    """Gemma 4 31B (Google, open weights) via OpenRouter free tier."""

    model_name = "google/gemma-4-31b-it:free"


@register_extractor("nemotron-nano-12b-vl")
class NemotronVL12BExtractor(OpenRouterExtractor):
    """NVidia Nemotron Nano 12B V2 VL via OpenRouter free tier."""

    model_name = "nvidia/nemotron-nano-12b-v2-vl:free"
