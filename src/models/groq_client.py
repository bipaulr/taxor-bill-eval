"""
Llama 4 Scout extractor via Groq API (OpenAI-compatible endpoint).

Groq free tier: no credit card required, all models available,
rate-limited (30 req/min, ~1000 req/day for this model).
Vision + JSON mode supported. See https://console.groq.com
"""

from typing import Any
import base64

from openai import OpenAI

from src.config import settings
from src.extractor import BaseExtractor, EXTRACTION_PROMPT, register_extractor


@register_extractor("llama-4-scout")
class GroqExtractor(BaseExtractor):
    """Extract bill data using Llama 4 Scout 17B (vision-capable) on Groq."""

    model_name = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Pricing as of July 2026 (USD per 1M tokens), from https://groq.com/pricing
    # Free tier costs $0; these are on-demand list prices for scaling estimates.
    input_price_per_1m = 0.11
    output_price_per_1m = 0.34

    def __init__(self):
        if not settings.groq_api_key:
            raise ValueError(
                "GROQ_API_KEY not set. Get a free key at "
                "https://console.groq.com/keys and add it to .env"
            )
        self.client = OpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
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
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
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
