"""
Claude Sonnet 4.6 extractor via Anthropic API.
"""

from typing import Any
import base64
import json

from anthropic import Anthropic

from src.config import settings
from src.extractor import BaseExtractor, EXTRACTION_PROMPT, register_extractor


@register_extractor("claude-sonnet-4-6")
class AnthropicExtractor(BaseExtractor):
    """Extract bill data using Claude Sonnet 4.6 (vision-capable)."""

    model_name = "claude-sonnet-4-20260514"

    # Pricing as of July 2026 (USD per 1M tokens)
    # $3.00 input / $15.00 output per 1M tokens
    input_price_per_1m = 3.00
    output_price_per_1m = 15.00

    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def _extract_impl(self, image_path: str) -> dict[str, Any]:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        b64 = base64.b64encode(image_bytes).decode("utf-8")

        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            temperature=0.1,
            system="You are a precise bill/receipt data extraction assistant. Return ONLY valid JSON.",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT,
                        },
                    ],
                }
            ],
        )

        self._last_input_tokens = response.usage.input_tokens if response.usage else 0
        self._last_output_tokens = response.usage.output_tokens if response.usage else 0

        # Extract the text content from the response
        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text
                break

        # Clean potential markdown fences
        raw = text.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        if raw.startswith("```"):
            raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]

        parsed = json.loads(raw.strip())
        parsed["_model"] = self.model_name
        parsed["_input_tokens"] = self._last_input_tokens
        parsed["_output_tokens"] = self._last_output_tokens
        return parsed

    def last_cost(self) -> float:
        input_cost = (self._last_input_tokens / 1_000_000) * self.input_price_per_1m
        output_cost = (self._last_output_tokens / 1_000_000) * self.output_price_per_1m
        return round(input_cost + output_cost, 8)

