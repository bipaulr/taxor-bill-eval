"""
GPT-4o extractor via OpenAI API.
"""

from typing import Any
import base64

from openai import OpenAI

from src.config import settings
from src.extractor import BaseExtractor, EXTRACTION_PROMPT, register_extractor


@register_extractor("gpt-4o")
class OpenAIExtractor(BaseExtractor):
    """Extract bill data using GPT-4o (vision-capable)."""

    model_name = "gpt-4o"

    # Pricing as of July 2026 (USD per 1M tokens)
    # $2.50 input / $10.00 output per 1M tokens
    input_price_per_1m = 2.50
    output_price_per_1m = 10.00

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)

    def extract(self, image_path: str) -> dict[str, Any]:
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
                            "image_url": {
                                "url": data_url,
                                "detail": "high",
                            },
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
