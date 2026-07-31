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

    @abstractmethod
    def extract(self, image_path: str) -> dict[str, Any]:
        """Send image to model, return parsed BillExtraction as dict."""
        ...

    def extract_structured(self, image_path: str) -> BillExtraction:
        """Returns a validated BillExtraction Pydantic model."""
        data = self.extract(image_path)
        return BillExtraction(**data)


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
    "gemini-2.5-flash": "src.models.gemini_client",
    "gpt-4o": "src.models.openai_client",
    "claude-sonnet-4-6": "src.models.anthropic_client",
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
