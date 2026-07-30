# Approach & Methodology

## Model Selection

Three vision-capable LLMs were selected based on availability via free/trial tiers and documented vision capabilities:

| Model | Provider | API Pricing (Input/Output per 1M tokens) | Trial Access |
|-------|----------|------------------------------------------|--------------|
| Gemini 2.5 Flash | Google AI Studio | $0.30 / $2.50 | Free tier (rate-limited) |
| GPT-4o | OpenAI | $2.50 / $10.00 | $5–18 trial credits |
| Claude Sonnet 4.6 | Anthropic | $3.00 / $15.00 | $5 trial credits |

**Why these three?** They span the price spectrum: Gemini 2.5 Flash is the budget champion, GPT-4o is the mid-range standard, and Claude Sonnet 4.6 is the premium option. Comparing across price points makes the cost/accuracy trade-off analysis meaningful.

**Pricing data source:** Verified against official provider pages on 2026-07-28.

## Dataset

**10–15 handwritten Indian bills/receipts** photographed by the author (personal/family bills from local shops). See `data/samples/` and `data/ground_truth/ground_truth.json`.

### Redaction
Before sending any image to an external API, sensitive Personally Identifiable Information (PII) is redacted:
- Phone numbers
- Full names of individuals (shop names are kept, as they're business-relevant)
- Bank account numbers / UPI IDs
- GST registration numbers (if they belong to an identifiable individual rather than a business)

Redaction was done manually using image editing software (Gaussian blur). The `scripts/redact_images.py` utility is provided for batch processing with pixel-region specification.

## Ground Truth & Scoring

### Definition of "Correct"

Each field uses a different match strategy, chosen to reflect the real-world cost of error:

| Field | Match Strategy | Rationale |
|-------|---------------|-----------|
| **vendor_name** | Fuzzy (Jaro-Winkler ≥ 0.85) | Handwritten names vary in spelling, abbreviation, and spacing. Exact match would penalize trivial differences like "Krishna Prov. Store" vs "Sri Krishna Provision Store". The 0.85 threshold means 85% character similarity — loosely tolerant. |
| **invoice_number** | Exact, or both null | Invoice numbers are precise identifiers. A wrong number is worse than no number. Partial credit is misleading here. |
| **date** | Exact (normalized to YYYY-MM-DD) | Dates are unambiguous when parsed. Partial credit (e.g. correct month but wrong day) is not useful for bookkeeping. |
| **amount** | Exact numeric (±0.01 tolerance) | Amounts must be precise for accounting. The 0.01 tolerance catches floating-point rounding without excusing real errors. |
| **currency** | Exact (ISO 4217) | Usually always INR for this dataset. Either correct or not. |
| **tax_gst** | Partial credit across sub-fields | Tax details have multiple parts (GST number, GST amount, taxable value). Scoring them as a single binary pass/fail would hide which sub-field the model struggles with. Each sub-field is scored independently, then averaged. |

### Important caveats

- **Null handling:** If a field is absent from the ground truth (e.g. no invoice number on a shop receipt), it's excluded from scoring for that bill. We only penalize models for fields that actually exist.
- **Illegibility flagging:** Models can mark fields as `illegible` in the output. This is noted but not currently scored as a separate metric — a model that says "I can't read this" is arguably better than one that hallucinates. This is a known gap (see Limitations).

## Cost Tracking

Cost is calculated per bill based on actual token usage from API responses:

```
cost = (input_tokens / 1_000_000) × input_price_per_1m
     + (output_tokens / 1_000_000) × output_price_per_1m
```

- Input tokens include the image tokens + text prompt tokens
- Output tokens are the model's response (JSON)
- Prices are per the official rate cards (July 2026)

Cost is reported as:
- **Cost per bill** — the average across all bills
- **Cost per 100 bills** — extrapolated (average × 100)

Note: Actual billed amounts may differ slightly due to:
- Free tier usage (Gemini is free via AI Studio, but we compute cost at paid rate for fair comparison)
- Prompt caching discounts (not applied here)
- Batch API discounts (not applied here)

## Pipeline Architecture

```
bill_image.jpg
    │
    ▼
┌─────────────────────────────┐
│  BaseExtractor (interface)  │  ← src/extractor.py
│  - extract(image_path)      │
│  - returns BillExtraction   │
└──────────┬──────────────────┘
           │
     ┌─────┼─────┐
     ▼     ▼     ▼
  Gemini  GPT-4o Claude
   2.5          Sonnet
   Flash        4.6
     │     │     │
     └─────┼─────┘
           ▼
┌─────────────────────────────┐
│      Evaluator              │  ← src/evaluator.py
│  - per-field scoring        │
│  - cost tracking            │
│  - accuracy/cost tables     │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│   Zoho Books Integration    │  ← src/zoho_integration.py
│   - OAuth2 + token refresh  │
│   - create_expense()        │
└─────────────────────────────┘
```

The common interface (`BaseExtractor`) ensures all models are called the same way. The `@register_extractor` decorator lets new models be added by simply creating a new class and registering it.

## Limitations (Honest)

1. **Small dataset (10–15 bills):** Results are indicative, not statistically significant. A model could get lucky or unlucky on this small sample.

2. **Ground truth is subjective:** I defined "correct" for each bill based on my own reading. Another person might interpret a smudged digit differently. This is inherent to handwritten documents.

3. **No illegibility scoring:** A model that returns `null` for an unreadable field is scored the same as a model that confidently returns the wrong value. A more sophisticated eval would reward appropriate uncertainty.

4. **Single prompt, no iteration:** Each model gets the exact same prompt with no few-shot examples or chain-of-thought. Better prompting could improve results for any model.

5. **No latency measurement:** For a real production pipeline, latency matters. We only track cost and accuracy.

6. **Currency/regional bias:** All bills are Indian rupees. The results may not generalize to other currencies or receipt formats.

7. **Free tier limitations:** Gemini's free tier has rate limits (5–15 RPM). For larger batches, paid tier would be needed.

## What I'd Do Differently With More Time

1. **Add illegibility scoring:** Track whether models appropriately flag uncertain fields as illegible rather than hallucinating.
2. **Multi-prompt strategies:** Try few-shot prompting and chain-of-thought to improve extraction.
3. **Stratified sampling:** More bills across different Indian states to test GST format variations.
4. **Human baseline:** Have a second person annotate the same bills to measure inter-annotator agreement on ground truth.
5. **Latency benchmarks:** Time each extraction to compare speed alongside cost and accuracy.
6. **Confidence scores:** Request confidence/probability scores per field from each model.
