# BillEval — Multi-Model Bill Extraction & Evaluation Framework

Extract structured data from handwritten Indian bills/receipts using 2–3 vision-capable LLMs, score extraction accuracy **per field per model**, track costs, and push results to Zoho Books.

Built for the Taxor Software Engineering Internship screening task.

## Setup

### Prerequisites
- Windows 10/11 with cmd or PowerShell
- Python 3.10+

### Installation

```cmd
cd C:\Users\hp\Desktop\taxor
py -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

Create `.env` from `.env.example` and fill in your API keys:

```cmd
copy .env.example .env
```

See docs for obtaining API keys:
- **Gemini**: https://aistudio.google.com/app/apikey (free tier available)
- **OpenAI**: https://platform.openai.com/api-keys (trial credits)
- **Anthropic**: https://console.anthropic.com/ (trial credits)
- **Zoho Books**: [docs/zoho_setup.md](docs/zoho_setup.md)

## Usage

### 1. Dataset — Collect & Redact Bills

1. Photograph 10–15 handwritten Indian bills/receipts
2. Redact PII (phone numbers, full names, account numbers) — manually or via:
   ```cmd
   py scripts\redact_images.py --input raw_photos --output data/samples
   ```
3. Place redacted images in `data/samples/`
4. Fill in `data/ground_truth/ground_truth.json` with correct field values

### 2. Run Extraction

```cmd
venv\Scripts\activate.bat
py run.py evaluate --models gemini-2.5-flash,gpt-4o,claude-sonnet-4-6
```

Or use the eval script directly:

```cmd
py eval\run_evaluation.py
```

### 3. Push to Zoho Books

First complete Zoho OAuth2 setup ([docs/zoho_setup.md](docs/zoho_setup.md)), then:

```cmd
py run.py zoho-push eval\results\extractions.json --max 5
```

## Project Structure

```
taxor/
├── run.py                    # CLI entry point
├── src/
│   ├── extractor.py          # Common interface: BaseExtractor, BillExtraction, prompt, registry
│   ├── models/
│   │   ├── gemini_client.py  # Gemini 2.5 Flash extractor
│   │   ├── openai_client.py  # GPT-4o extractor
│   │   └── anthropic_client.py # Claude Sonnet 4.6 extractor
│   ├── evaluator.py          # Per-field scoring + cost tracking
│   ├── config.py             # .env loading via pydantic-settings
│   ├── redact.py             # PII redaction utilities (PIL)
│   └── zoho_integration.py   # Zoho Books API client + expense creation
├── data/
│   ├── samples/              # Redacted bill images (you provide)
│   └── ground_truth/         # ground_truth.json
├── eval/
│   ├── run_evaluation.py     # CLI script to run full eval pipeline
│   └── results/              # Output CSVs (auto-generated)
├── docs/
│   ├── approach.md           # Detailed methodology & trade-off write-up
│   └── zoho_setup.md         # Zoho Books OAuth2 setup guide
├── scripts/
│   └── redact_images.py      # PII blurring utility
├── .env.example
├── .gitignore
└── requirements.txt
```

## Models

| Model | Provider | API Name | Input Price / 1M tok | Output Price / 1M tok | Trial Access |
|-------|----------|----------|---------------------|----------------------|-------------|
| Gemini 2.5 Flash | Google | `gemini-2.5-flash` | $0.30 | $2.50 | Free tier (rate-limited) |
| GPT-4o | OpenAI | `gpt-4o` | $2.50 | $10.00 | $5–18 trial credits |
| Claude Sonnet 4.6 | Anthropic | `claude-sonnet-4-20260514` | $3.00 | $15.00 | $5 trial credits |

*Pricing verified 2026-07-28.*

## Evaluation Methodology

**Key principle:** Per-field accuracy, never a single blended score. Each field type uses a different match strategy:

| Field | Match Strategy | Rationale |
|-------|---------------|-----------|
| Vendor Name | Fuzzy (Jaro-Winkler ≥ 0.85) | Handwritten names vary in spelling/abbreviation |
| Invoice Number | Exact, or both null | Precise identifiers; wrong is worse than null |
| Date | Exact (normalized YYYY-MM-DD) | Must be correct for accounting |
| Amount | Exact numeric (±0.01 tolerance) | Must match for expense reporting |
| Currency | Exact (ISO 4217) | Binary correct/incorrect |
| Tax/GST | Partial credit across sub-fields | GST number, amount, taxable value scored separately |

### Accuracy Table

| Field | Gemini 2.5 Flash | GPT-4o | Claude Sonnet 4.6 |
|-------|-----------------|--------|-------------------|
| Vendor Name | — | — | — |
| Invoice Number | — | — | — |
| Date | — | — | — |
| Amount | — | — | — |
| Currency | — | — | — |
| Tax/GST | — | — | — |
| **Cost/bill** | — | — | — |
| **Cost/100 bills** | — | — | — |

*To be filled after running evaluation.*

## Recommendation

> *(To be written after evaluation — see docs/approach.md for the methodology that will drive this decision.)*

## Limitations

See [docs/approach.md](docs/approach.md) for a full honest discussion. Key gaps:
1. Small dataset (10–15 bills) — results are indicative, not statistically significant
2. Ground truth is subjective — based on my reading of handwritten digits
3. No illegibility scoring — returning null vs hallucinating is treated the same
4. Single prompt, no iteration — better prompts could improve any model

## License

MIT
