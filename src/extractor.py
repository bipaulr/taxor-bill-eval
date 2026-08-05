"""
Common extraction interface.

All model clients implement `extract(image_path: str) -> dict` returning
structured JSON matching the BillExtraction model.

Usage:
    extractor = get_extractor("gemini-2.5-flash")
    result = extractor.extract("data/samples/bill_001.jpg")
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class TaxGST(BaseModel):
    """Tax/GST details extracted from a bill."""

    gst_number: str | None = None
    gst_amount: float | None = None
    taxable_value: float | None = None


class BillExtraction(BaseModel):
    """Structured output expected from every vision model."""

    vendor_name: str | None = None
    invoice_number: str | None = None
    date: str | None = None  # ISO format YYYY-MM-DD
    amount: float | None = None
    currency: str | None = "INR"  # ISO 4217
    tax_gst: TaxGST | None = None

    # Language of the bill text (e.g. "en", "ml" for Malayalam)
    language: str | None = None

    # Confidence / legibility flag
    illegible_fields: list[str] = []
    raw_text: str | None = None  # model's free-text notes


# The prompt used for all models (minimal changes per provider syntax)
EXTRACTION_PROMPT = """You are a bill/receipt data extraction assistant. Extract the following fields from this Indian bill image and return ONLY valid JSON (no markdown, no explanation) with this exact schema:

{
  "vendor_name": "Shop or vendor name, written EXACTLY as on the bill (keep the original script, e.g. Malayalam if written in Malayalam). If not visible, null",
  "invoice_number": "Bill/invoice number if present, else null",
  "date": "Date in YYYY-MM-DD format (if visible, else null)",
  "amount": "Total amount as a number (0.00 format, if visible, else null)",
  "currency": "Currency code (e.g. INR, USD) — default to INR if Indian bill",
  "tax_gst": {
    "gst_number": "GST registration number if visible, else null",
    "gst_amount": "Total GST/tax amount as a number if visible, else null",
    "taxable_value": "Taxable value before tax if visible, else null"
  },
  "language": "Language of the bill's main text (ISO 639-1, e.g. 'en', 'ml', 'hi')",
  "illegible_fields": ["list any fields above that are cut off, smudged, or unreadable"],
  "raw_text": "Any additional free-text observations about the bill"
}

Important rules:
- If a field is not visible or readable, set it to null — do not make up values. Never invent an invoice number or GST number.
- vendor_name must keep the ORIGINAL script and spelling exactly as printed/written (do not transliterate).
- For amounts, extract the numeric value without currency symbols.
- For dates, convert to YYYY-MM-DD. If month/day order is ambiguous, use Indian convention (DD/MM/YYYY).
- List any fields you're uncertain about in the illegible_fields array.
- Return ONLY the JSON object, nothing else."""


class BaseExtractor(ABC):
    """Every model client inherits from this."""

    model_name: str
    # Rate-limit handling: how many times to retry a request that hits a
    # 429 (quota/rate-limit) error, and the base seconds between retries.
    max_retries: int = 3
    retry_base_delay: float = 20.0

    @abstractmethod
    def _extract_impl(self, image_path: str) -> dict[str, Any]:
        """Provider-specific extraction logic. Subclasses implement this."""
        ...

    def extract(self, image_path: str) -> dict[str, Any]:
        """Send image to model, return parsed BillExtraction as dict.

        Wraps _extract_impl with retry-on-rate-limit logic. The free tiers
        of Gemini/OpenAI/Anthropic all enforce per-minute AND per-day request
        limits. We retry transient (per-minute) limits with a short backoff,
        but bail out fast on per-day quota exhaustion (retrying is useless
        until the quota resets).
        """
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._extract_impl(image_path)
            except Exception as e:  # noqa: BLE001 - retry all provider errors
                last_error = e
                if not self._is_rate_limit(e) or attempt >= self.max_retries:
                    break
                retry_after = self._retry_after_seconds(e)
                if retry_after is None:
                    # Ambiguous — treat as daily quota exhaustion, bail.
                    break
                delay = min(retry_after, self.retry_base_delay * (2**attempt))
                print(f"    Rate limited, retrying in {delay:.0f}s "
                      f"(attempt {attempt + 1}/{self.max_retries})...")
                import time
                time.sleep(delay)
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _is_rate_limit(e: Exception) -> bool:
        """Heuristic: 429 / RESOURCE_EXHAUSTED / rate_limit means rate-limited."""
        msg = str(e).lower()
        return any(
            kw in msg
            for kw in ("429", "resource_exhausted", "rate limit", "rate_limit",
                       "quota", "too many requests", "429 too_many_requests",
                       "empty response", "not a json object")
        )

    @staticmethod
    def _retry_after_seconds(e: Exception) -> float | None:
        """
        Parse the retry delay from a rate-limit error, if the provider
        suggests one. Return None if the limit appears to be a per-day
        (non-recoverable-in-seconds) quota.
        """
        msg = str(e).lower()
        import re
        # Daily-quota exhaustion is NOT recoverable with a short retry —
        # return None so the caller bails out immediately.
        # Gemini quota ids look like ".../GenerateRequestsPerDayPerProject...".
        # OpenRouter shared free budget: "...free-models-per-day...".
        if ("perday" in msg or "per_day" in msg or "requests_per_day" in msg
                or "per-day" in msg or "per day" in msg):
            return None
        # OpenRouter :free models hit transient upstream congestion
        # ("temporarily rate-limited upstream"). Retryable with a short wait.
        if "temporarily rate-limited" in msg or "rate-limited upstream" in msg:
            return 15.0
        # Empty / malformed model output on flaky free endpoints — retryable.
        if "empty response" in msg or "not a json object" in msg:
            return 8.0
        # "retry in 23.117s" / "retry in 55.4s"
        m = re.search(r"retry(?:ing)? in ([\d.]+)s", msg)
        if m:
            return float(m.group(1))
        # Gemini per-minute 429 errors embed a RetryInfo.retryDelay.
        m = re.search(r"retrydelay': '([\d.]+)s'", msg)
        if m:
            return float(m.group(1))
        return None

    def extract_structured(self, image_path: str) -> BillExtraction:
        """Returns a validated BillExtraction Pydantic model."""
        data = self.extract(image_path)
        return BillExtraction(**data)


def parse_json_response(text: str | list | None) -> dict[str, Any]:
    """Parse model output into a dict, tolerating markdown code fences.

    Some providers (Gemini, Gemma via OpenRouter) wrap the JSON in
    ```json ... ``` fences; some append trailing prose. Some return
    content as a list of parts. Strip/handle all of these.
    """
    import json
    import re

    if isinstance(text, list):
        # OpenRouter multimodal responses can be a list of content parts.
        parts = [p.get("text") if isinstance(p, dict) else str(p) for p in text]
        text = "\n".join(p for p in parts if p)

    raw = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*", raw)
    if fence:
        raw = raw[fence.end():]
    if raw.endswith("```"):
        raw = raw[:-3].rstrip()
    if not raw:
        raise ValueError("Empty model response")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fall back to the first balanced JSON object in the response.
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        result = json.loads(raw[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("Model response is not a JSON object")
    return result


# Registry of available extractors
_registry: dict[str, type[BaseExtractor]] = {}


def register_extractor(name: str):
    """Decorator to register an extractor class."""

    def wrapper(cls: type[BaseExtractor]):
        _registry[name] = cls
        return cls

    return wrapper


# Model name to module path mapping (for lazy loading)
_MODEL_MODULES = {
    "gemini-3.1-flash-lite": "src.models.gemini_client",
    "gemini-3-flash-preview": "src.models.gemini_client",
    "gemma-4-31b": "src.models.openrouter_client",
    "nemotron-nano-12b-vl": "src.models.openrouter_client",
}


def _ensure_model_loaded(name: str):
    """Import the model module so its @register_extractor decorator runs."""
    if name not in _registry:
        module_path = _MODEL_MODULES.get(name)
        if module_path:
            import importlib
            importlib.import_module(module_path)
        if name not in _registry:
            available = ", ".join(_registry.keys())
            raise ValueError(
                f"Unknown model '{name}'. Available: {available}"
            )


def get_extractor(name: str) -> BaseExtractor:
    """Get an extractor instance by model name."""
    _ensure_model_loaded(name)
    return _registry[name]()

