"""
Gemini 3.1 Flash Lite extractor via Google AI Studio / Gemini API.

NOTE: Gemini free tier enforces a daily quota of ~20 requests PER MODEL.
Switch model names to get a fresh daily pool.
"""

import base64
from typing import Any

from google import genai
from google.genai import types

from src.config import settings
from src.extractor import BaseExtractor, EXTRACTION_PROMPT, register_extractor


@register_extractor("gemini-3.1-flash-lite")
class Gemini31FlashLiteExtractor(BaseExtractor):
    """Extract bill data using Gemini 3.1 Flash Lite (vision-capable)."""

    model_name = "gemini-3.1-flash-lite"

    # Pricing as of July 2026 (USD per 1M tokens), verified 2026-07-31
    # from https://ai.google.dev/gemini-api/docs/pricing
    # Free tier available; paid tier: $0.25 input / $1.50 output per 1M tokens
    input_price_per_1m = 0.25
    output_price_per_1m = 1.50

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)

    def _extract_impl(self, image_path: str) -> dict[str, Any]:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type="image/jpeg",
                        ),
                        types.Part(text=EXTRACTION_PROMPT),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        # Track token usage for cost calculation
        if response.usage_metadata:
            self._last_input_tokens = response.usage_metadata.prompt_token_count or 0
            self._last_output_tokens = response.usage_metadata.candidates_token_count or 0
        else:
            self._last_input_tokens = 0
            self._last_output_tokens = 0

        raw = response.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        if raw.startswith("```"):
            raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]

        import json
        parsed = json.loads(raw.strip())
        parsed["_model"] = self.model_name
        parsed["_input_tokens"] = self._last_input_tokens
        parsed["_output_tokens"] = self._last_output_tokens
        return parsed

    def last_cost(self) -> float:
        """Cost of the last extraction in USD."""
        input_cost = (self._last_input_tokens / 1_000_000) * self.input_price_per_1m
        output_cost = (self._last_output_tokens / 1_000_000) * self.output_price_per_1m
        return round(input_cost + output_cost, 8)


@register_extractor("gemini-3-flash-preview")
class Gemini3FlashPreviewExtractor(Gemini31FlashLiteExtractor):
    """Gemini 3 Flash (preview) — same API, separate free-tier daily quota."""

    model_name = "gemini-3-flash-preview"

