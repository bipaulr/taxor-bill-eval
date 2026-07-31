# BillEval — Multi-Model Bill Extraction & Evaluation

Extract structured data from **handwritten Indian bills** using multiple
vision-capable LLMs, score extraction accuracy **per field per model**, track
costs, and push results to Zoho Books.

Built for the Taxor Software Engineering Internship screening task.

- **Full methodology & trade-offs:** [docs/approach.md](docs/approach.md)
- **Zoho Books OAuth setup:** [docs/zoho_setup.md](docs/zoho_setup.md)
- **Bonus UI:** upload a bill and compare models side-by-side (see below)

---

## Results snapshot

### Handwritten bills (13) — accuracy % per field

| Model | vendor | invoice# | date | amount | currency | tax/GST | bills |
|-------|--------|----------|------|--------|----------|---------|-------|
| Gemini 3.1 Flash Lite | 100.0 | 53.8 | 38.5 | 92.3 | 100.0 | 92.3 | 13 |
| Nemotron Nano 12B VL | 92.3 | 46.2 | 38.5 | 84.6 | 100.0 | 92.3 | 13 |
| Gemma 4 31B | *pending* | | | | | | |
| Gemini 3 Flash Preview | *pending* | | | | | | |

### Cost per bill (paid-tier list price; actual spend was $0 on free tiers)

| Model | cost/bill | cost/100 bills |
|-------|-----------|----------------|
| Gemini 3.1 Flash Lite | $0.00066 | $0.0656 |
| Nemotron Nano 12B VL | ~$0.00011 | ~$0.011 |
| Gemma 4 31B | ~$0.00015 | ~$0.015 |

Full numbers: `eval/results/*.csv`.

---

## Setup

### Prerequisites
- Windows / Linux / macOS, Python 3.10+
- API keys for whichever models you want (all have free tiers)

### Install

```bash
python -m venv venv
venv\Scripts\activate.bat        # Windows  (or: source venv/bin/activate)
pip install -r requirements.txt
```

### Configure

```bash
copy .env.example .env           # Windows (or: cp .env.example .env)
```

Then fill in the keys you have:

| Key | Where to get it | Free tier |
|-----|-----------------|-----------|
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey | ~20 req/day |
| `OPENROUTER_API_KEY` | https://openrouter.ai/settings/keys | 50 req/day (all free models, shared) |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | provider consoles | trial credits |
| `ZOHO_*` | see [docs/zoho_setup.md](docs/zoho_setup.md) | free plan |

Never commit your `.env` — it is git-ignored.

## Dataset

- **13 handwritten Indian bills** in `data/samples/` (11 English, 2 Malayalam),
  redacted (PII blurred) before any API call. Originals live in `raw_photos/`
  (git-ignored).
- **3 synthetic typed invoices** in `data/samples_digital/` (for the
  digital-vs-handwritten question).
- Ground truth: `data/ground_truth/ground_truth.json` (+ `_digital.json`).

## Usage

### 1. Run a full evaluation

```bash
# Handwritten set — default models (Gemini + 2 OpenRouter free models)
py run.py evaluate --delay 3

# Or pick models explicitly
py run.py evaluate --models gemini-3.1-flash-lite,nemotron-nano-12b-vl --delay 3

# Digital set
py run.py evaluate --gt data/ground_truth/ground_truth_digital.json \
    --samples data/samples_digital --dataset digital --delay 3

# Also save raw predictions (needed for Zoho push)
py run.py evaluate --save-predictions --delay 3
```

Results land in `eval/results/` (`accuracy_summary.csv`, `cost_summary.csv`,
`per_bill_scores.csv`, `predictions/`). Multiple runs **merge** — re-running a
model updates only its rows.

### 2. Push extractions to Zoho Books

```bash
# after Zoho OAuth setup (docs/zoho_setup.md) and running with --save-predictions
py run.py zoho-push eval/results/predictions/handwritten_gemini-3.1-flash-lite.json --max 5
```

### 3. Bonus UI — compare models on your own bill

```bash
uvicorn app:app --port 8000        # then open http://localhost:8000
```

Upload any bill image → all configured models extract it → see fields side by
side. Model set via `UI_MODELS` (default:
`gemini-3.1-flash-lite,gemma-4-31b,nemotron-nano-12b-vl`). Use `UI_MOCK=1` to
demo without API access when quotas are exhausted.

## Project structure

```
taxor/
├── app.py                       # Bonus UI (FastAPI)
├── ui/index.html                # UI page
├── run.py                       # CLI: evaluate / extract / zoho-push / redact
├── src/
│   ├── extractor.py             # BaseExtractor, prompt, registry, retry logic
│   ├── evaluator.py             # per-field scoring + cost tracking
│   ├── config.py                # .env loading
│   ├── zoho_integration.py      # Zoho Books client
│   └── models/                  # one module per provider
│       ├── gemini_client.py     # Gemini 3.1 Flash Lite
│       ├── openrouter_client.py # Gemma 4 31B + Nemotron Nano 12B VL (:free)
│       ├── groq_client.py       # Llama 4 Scout (no vision on free tier — kept for reference)
│       ├── openai_client.py     # GPT-4o (trial credits exhausted)
│       └── anthropic_client.py  # Claude (trial credits exhausted)
├── data/
│   ├── samples/                 # redacted handwritten bills
│   ├── samples_digital/         # synthetic typed invoices
│   └── ground_truth/            # ground_truth.json (+ _digital.json)
├── scripts/
│   ├── redact_images.py         # PII blurring utility
│   └── digital_bills/           # HTML sources for the 3 synthetic invoices
├── eval/results/                # accuracy/cost/per-bill CSVs (auto-generated)
├── docs/approach.md             # methodology + recommendation rationale
└── docs/zoho_setup.md
```

## Evaluation methodology (summary)

- **Per-field accuracy, never one blended number.**
- vendor: fuzzy (Jaro-Winkler ≥ 0.85) · invoice/date/currency: exact ·
  amount: numeric ±0.01 · tax/GST: partial credit across 3 sub-fields.
- **Hallucination penalty:** if ground truth is null (e.g. no invoice number),
  the model must return null — inventing a value scores 0.
- Cost = token usage × provider rate card, reported per bill and per 100 bills,
  plus paid-tier extrapolation.

Full rationale: [docs/approach.md](docs/approach.md).

## Recommendation (preliminary — finalizes after pending runs)

Based on complete data: **Gemini 3.1 Flash Lite** reads handwritten bills most
accurately (100% vendor, 92.3% amount) for ~$0.066 per 100 bills at list price.
**Nemotron Nano 12B VL** is a credible **$0** fallback (92.3% / 84.6%) if cost
matters more than a few points of accuracy — and it nailed the digital set
(100% everywhere), suggesting a cheap open model may be enough for typed docs
while the stronger model is reserved for handwriting.

The pending Gemma / Flash Preview runs will confirm whether this holds.

## Limitations

See [docs/approach.md](docs/approach.md) — the short version:
small dataset, subjective ground truth, no illegibility-scoring, single prompt,
free-tier flakiness, synthetic digital set.

## License

MIT
