# Approach & Methodology

## Objective

Taxor needs handwritten Indian bills converted into structured expense entries
(vendor, invoice number, date, amount, currency, tax/GST). This project answers
two questions with data:

1. Which vision LLM actually reads handwritten bills best?
2. Does the accuracy gain justify the cost?

## Model Selection

Four vision-capable models were selected based on what was *actually usable* via
free/trial tiers on the evaluation day. OpenAI (GPT-4o) and Anthropic (Claude)
were originally planned but their trial credits were exhausted before any runs
completed, so they were dropped and replaced with free open-weight alternatives.

| Model | Provider | List price (in/out per 1M tok) | Access used | Status |
|-------|----------|-------------------------------|-------------|--------|
| Gemini 3.1 Flash Lite | Google AI Studio | $0.25 / $1.50 | Free tier (20 req/day) | ✅ full run |
| Gemini 3 Flash Preview | Google AI Studio | $0.25 / $1.50 | Free tier | 🔄 partial |
| Nemotron Nano 12B VL | NVIDIA (via OpenRouter `:free`) | $0.11 / $0.34 (paid endpoint) | OpenRouter free (50 req/day, shared) | ✅ full run |
| Gemma 4 31B | Google (via OpenRouter `:free`) | $0.25 / $0.80 (paid endpoint) | OpenRouter free | 🔄 1/13 so far |

> **Honest note on pricing:** the models marked "free tier" cost **$0 actual
> spend** in this project. The *list prices* are what a production deployment
> would pay once free quotas (rate limits) stop being sufficient — we report
> both so the cost argument is grounded, not vibes.

**Free-tier realities discovered (documented so nobody repeats our surprise):**
- Gemini free tier: ~20 requests/day shared across ALL model names on the account.
- OpenRouter free tier: **50 requests/day shared across all `:free` models per
  account** (the docs often quote "200/model" — our account was capped at 50 total).
- Groq free tier: no vision models exposed on a new free account (text/whisper only).

## Dataset

### Handwritten (the core set) — 13 bills
Photographed real bills from local shops (personal/family expenses). See
`data/samples/` and `data/ground_truth/ground_truth.json`.

- 11 English, 2 Malayalam (bills 09, 13). Bill 09 is mixed: items in Malayalam,
  vendor name printed in English ("M.S Fruits & Vegetables").
- No bill has GST or a reliable invoice number — which makes the
  `invoice_number` / `tax_gst` scores a measure of **model honesty** (see scoring).
- Deliberate variety: different handwriting styles, paper quality, lighting.

### Digital (supporting set) — 3 synthetic typed invoices
Added to answer the task's "same model for digital AND handwritten?" question.
These are machine-generated typed invoices (`scripts/digital_bills/*.html`
rendered via headless Edge) in three distinct formats:
grocery GST invoice, pharmacy bill (no GST), restaurant bill.
See `data/samples_digital/` and `data/ground_truth/ground_truth_digital.json`.

> Limitation: synthetic = clean, high-contrast, perfectly legible. Real scanned
> invoices can be skewed, low-res, or cluttered. Our digital numbers are thus an
> **upper bound** on typed-document performance.

### Redaction
All images are redacted before any API call: phone numbers, individual names,
bank/UPI details blurred (Gaussian). Shop names kept (business-relevant).
The `scripts/redact_images.py` utility is provided; the original unredacted
photos are git-ignored and never committed.

## Ground Truth & Scoring

### Definition of "correct"

| Field | Match strategy | Rationale |
|-------|---------------|-----------|
| vendor_name | Fuzzy (Jaro-Winkler ≥ 0.85) | Handwritten names vary in spelling/abbreviation; exact match would over-penalise |
| invoice_number | Exact, or both null | Precise identifiers; a wrong number is worse than none |
| date | Exact (normalized YYYY-MM-DD) | Must be right for accounting |
| amount | Exact numeric (±0.01) | Expense reporting needs exact totals |
| currency | Exact (ISO 4217) | Binary |
| tax_gst | Partial credit across 3 sub-fields | GST number / amount / taxable value scored separately, then averaged |

### The hallucination penalty (key design choice)

**Null in ground truth ⇒ the model must return null.** Most bills have no
invoice number and no GST; a model that *invents* one scores 0. This means
`invoice_number` and `tax_gst` accuracy is a measure of **honesty**, not just
reading skill — and it directly penalizes the failure mode that would pollute a
real accounting system (booking a fake invoice number / GST amount).

### Cost tracking

```
cost = (input_tokens/1e6) × input_price_per_1m + (output_tokens/1e6) × output_price_per_1m
```

Reported as **cost/bill** and **cost/100 bills** (extrapolated). We also show a
"paid-tier" extrapolation for the open models so a decision isn't made on the
free-tier honeymoon alone.

## Results (as of 31 Jul, pending final runs)

### Handwritten — accuracy % per field

| Model | vendor | invoice# | date | amount | currency | tax/GST | bills |
|-------|--------|----------|------|--------|----------|---------|-------|
| Gemini 3.1 Flash Lite | 100.0 | 53.8 | 38.5 | 92.3 | 100.0 | 92.3 | 13 |
| Nemotron Nano 12B VL | 92.3 | 46.2 | 38.5 | 84.6 | 100.0 | 92.3 | 13 |
| Gemma 4 31B | 100.0* | 100.0* | 100.0* | 100.0* | 100.0* | 100.0* | 1* |
| Gemini 3 Flash Preview | 100.0* | 66.7* | 50.0* | 100.0* | 100.0* | 100.0* | 6* |

\* pending full run (free-tier daily quotas exhausted mid-run).

### Digital (3 synthetic) — accuracy % per field

| Model | vendor | invoice# | date | amount | currency | tax/GST | bills |
|-------|--------|----------|------|--------|----------|---------|-------|
| Nemotron Nano 12B VL | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 100.0 | 3 |
| *(Gemini / Gemma pending)* | — | — | — | — | — | — | — |

### Cost

| Model | actual spend | cost/bill (paid tier) | cost/100 bills |
|-------|--------------|------------------------|----------------|
| Gemini 3.1 Flash Lite | $0 (free quota) | $0.00066 | $0.0656 |
| Nemotron Nano 12B VL | $0 (free) | ~$0.00011 | ~$0.011 |
| Gemma 4 31B | $0 (free) | ~$0.00015 | ~$0.015 |

## Pipeline Architecture

```
bill_image.jpg
    │
    ▼
┌───────────────────────────────┐
│ BaseExtractor (interface)     │  ← src/extractor.py
│  - extract(image_path)        │  - retry/rate-limit handling
│  - returns BillExtraction     │  - registry (@register_extractor)
└──────────────┬────────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
   Gemini   Nemotron  Gemma
   3.1      Nano     4 31B
   Flash     12B VL   (OpenRouter)
   Lite     (OpenRouter)
       │       │        │
       └───────┼────────┘
               ▼
┌───────────────────────────────┐
│ Evaluator                     │  ← src/evaluator.py
│  - per-field scoring          │
│  - cost tracking              │
│  - accuracy/cost tables       │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│ Zoho Books integration        │  ← src/zoho_integration.py
│  - OAuth2 + token refresh     │
│  - create expense from fields │
└───────────────────────────────┘
```

All models get the **same prompt** (`EXTRACTION_PROMPT` in `src/extractor.py`)
and the same `temperature=0.1`, JSON-mode request. The registry pattern means a
new model is added by writing one class — no pipeline changes.

## Limitations (Honest)

1. **Small dataset (13 handwritten + 3 digital).** Indicative, not statistically
   significant. One bad bill can move a metric ~8 points.
2. **Ground truth is subjective** — one person's reading of smudged handwriting.
3. **No illegibility scoring.** Returning `null` vs inventing a value is
   *penalized differently* (null when truth is null = correct; hallucination = 0),
   but we don't separately reward a model for *flagging* uncertainty via
   `illegible_fields`. Known gap.
4. **Single prompt, no few-shot / CoT.** Every model could improve with tuning.
5. **No latency measurement.**
6. **Regional bias** — all Indian bills, INR. Results may not generalize.
7. **Synthetic digital invoices** — clean renders; real scanned documents are messier.
8. **Free-tier flakiness** — OpenRouter `:free` endpoints return transient
   errors/congestion; our retry logic handles it but it's noisy and could bias
   results if a bill only succeeds after retries.

## What I'd Do Differently With More Time

1. **Illegibility scoring** (reward "I can't read this" over confident guessing).
2. **Multi-prompt strategies** (few-shot, CoT) — the single-prompt setup probably
   understates what each model can do.
3. **Bigger, stratified dataset** (more states, GST-format variety, tilted/skewed scans).
4. **Second annotator** for inter-annotator agreement on ground truth.
5. **Latency benchmarks** alongside cost and accuracy.
6. **Ensembling / confidence routing** — send only the hard cases to the premium model.
