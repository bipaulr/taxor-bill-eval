"""Bonus UI: upload a bill image and compare vision models side by side.

Run:
    venv\\Scripts\\activate.bat
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000

The default model set is configurable via the UI_MODELS env var
(comma-separated extractor names, e.g. "gemini-3.1-flash-lite,nemotron-nano-12b-vl").
Set UI_MOCK=1 to return canned sample data instead of calling the APIs
(handy for a demo when free-tier quotas are exhausted).
"""

import io
import json
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from src.extractor import get_extractor

DEFAULT_MODELS = ["gemini-3.1-flash-lite", "gemma-4-31b", "nemotron-nano-12b-vl"]
MODELS = [
    m.strip()
    for m in os.environ.get("UI_MODELS", ",".join(DEFAULT_MODELS)).split(",")
    if m.strip()
]
MOCK = os.environ.get("UI_MOCK", "0") == "1"

app = FastAPI(title="BillEval — Multi-Model Bill Extraction Comparison")

FIELDS = [
    "vendor_name",
    "invoice_number",
    "date",
    "amount",
    "currency",
    "tax_gst",
    "language",
    "illegible_fields",
    "raw_text",
]

FIELD_LABELS = {
    "vendor_name": "Vendor",
    "invoice_number": "Invoice #",
    "date": "Date",
    "amount": "Amount",
    "currency": "Currency",
    "tax_gst": "Tax / GST",
    "language": "Language",
    "illegible_fields": "Illegible fields",
    "raw_text": "Raw notes",
}


def _format_value(value):
    """Render an extracted field value for display."""
    if value is None:
        return '<span class="null">—</span>'
    if isinstance(value, (dict, list)):
        return "<code>" + json.dumps(value, ensure_ascii=False) + "</code>"
    return str(value)


def _mock_result():
    """Canned response used when UI_MOCK=1."""
    sample = {
        "vendor_name": "Krishna Provision Store",
        "invoice_number": None,
        "date": "2026-07-07",
        "amount": 500.00,
        "currency": "INR",
        "tax_gst": {"gst_number": None, "gst_amount": None, "taxable_value": None},
        "language": "en",
        "illegible_fields": ["invoice_number"],
        "raw_text": "MOCK data — quotas exhausted.",
    }
    return sample


def _run_models(image_path: str) -> dict:
    results = {}
    for name in MODELS:
        if MOCK:
            data = _mock_result()
            results[name] = {
                "fields": data,
                "tokens": {"in": 2100, "out": 180},
                "cost": 0.0,
                "error": None,
            }
            continue
        try:
            extractor = get_extractor(name)
            data = extractor.extract(image_path)
            results[name] = {
                "fields": data,
                "tokens": {
                    "in": data.get("_input_tokens", 0),
                    "out": data.get("_output_tokens", 0),
                },
                "cost": extractor.last_cost(),
                "error": None,
            }
        except Exception as e:  # noqa: BLE001 — surface any provider error to the UI
            results[name] = {
                "fields": {},
                "tokens": {"in": 0, "out": 0},
                "cost": 0.0,
                "error": str(e)[:300],
            }
    return results


@app.get("/", response_class=HTMLResponse)
def index():
    return Path("ui/index.html").read_text(encoding="utf-8")


@app.post("/api/extract")
async def api_extract(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(
        (".jpg", ".jpeg", ".png", ".webp")
    ):
        raise HTTPException(status_code=400, detail="Please upload a JPG/PNG/WEBP image.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        results = _run_models(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"filename": file.filename, "models": MODELS, "results": results}
