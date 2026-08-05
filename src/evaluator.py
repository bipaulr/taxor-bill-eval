"""
Evaluation framework: per-field scoring, cost tracking, comparison tables.

Match strategies per field type (documented and defensible):
- vendor_name:    Fuzzy (Jaro-Winkler, threshold >= 0.85).
                  Handwritten shop names vary in spelling, spacing, abbreviation.
                  Exact match would penalise "Krishna Provision Store" vs "Sri Krishna Prov. Store".
- invoice_number: Exact match or both null. Invoice numbers are precise identifiers.
- date:           Exact match after normalization to YYYY-MM-DD.
                  A wrong date is clearly wrong; no partial credit.
- amount:         Numeric tolerance ±0.01 within same currency.
                  Off-by-one errors in handwritten totals are rare; tolerance catches
                  minor rounding differences.
- currency:       Exact match (ISO 4217). Usually always INR for this dataset.
- tax_gst:        Partial credit. Each sub-field (gst_number, gst_amount, taxable_value)
                  scored independently, then averaged into one tax_gst score.
"""

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from src.extractor import BillExtraction, get_extractor


# ---------- Fuzzy matching for vendor names ----------

def jaro_winkler(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity (0.0–1.0). Hand-rolled, no deps needed."""
    if not s1 or not s2:
        return float(s1 == s2)
    # Jaro
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    match_dist = max(len(s1), len(s2)) // 2 - 1
    match_dist = max(match_dist, 0)

    s1_matches = [False] * len(s1)
    s2_matches = [False] * len(s2)
    matches = 0
    transpositions = 0

    for i in range(len(s1)):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len(s2))
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len(s1)):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        matches / len(s1)
        + matches / len(s2)
        + (matches - transpositions / 2) / matches
    ) / 3

    # Winkler prefix boost (first 4 chars matching)
    prefix = 0
    for i in range(min(4, min(len(s1), len(s2)))):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + 0.1 * prefix * (1 - jaro)


# ---------- Score a single field ----------

# Thresholds per field
FUZZY_THRESHOLD = 0.85


def score_vendor_name(pred: str | None, truth: str | None) -> float:
    # Correct semantics: if the field doesn't exist on the bill (truth None),
    # the model must also return None. Inventing a value is a hallucination → 0.
    if truth is None:
        return 1.0 if pred is None else 0.0
    if pred is None:
        return 0.0
    if truth.lower().strip() == pred.lower().strip():
        return 1.0
    return 1.0 if jaro_winkler(pred, truth) >= FUZZY_THRESHOLD else 0.0


def score_exact(pred: str | float | None, truth: str | float | None) -> float:
    if truth is None:
        return 1.0 if pred is None else 0.0
    if pred is None:
        return 0.0
    return 1.0 if str(pred).strip() == str(truth).strip() else 0.0


def score_amount(pred: float | None, truth: float | None) -> float:
    if truth is None:
        return 1.0 if pred is None else 0.0
    if pred is None:
        return 0.0
    return 1.0 if abs(float(pred) - float(truth)) <= 0.01 else 0.0


def score_date(pred: str | None, truth: str | None) -> float:
    """Exact match after normalizing both to YYYY-MM-DD."""
    if truth is None:
        return 1.0 if pred is None else 0.0
    if pred is None:
        return 0.0
    # Normalize: remove leading/trailing whitespace
    return 1.0 if pred.strip() == truth.strip() else 0.0


def score_tax_gst(pred: dict | None, truth: dict | None) -> float:
    """Partial credit across gst_number, gst_amount, taxable_value."""
    # If no tax details exist on the bill, the model must not invent any.
    truth_has_none = truth is None or all(v is None for v in (truth or {}).values())
    if truth_has_none:
        pred_has_something = bool(pred) and any(
            v is not None for v in pred.values()
        )
        return 1.0 if not pred_has_something else 0.0

    pred = pred or {}
    sub_scores = []
    for key in ["gst_number", "gst_amount", "taxable_value"]:
        p = pred.get(key)
        t = truth.get(key)
        if t is None:
            sub_scores.append(1.0)  # nothing to extract for this sub-field
        elif p is None:
            sub_scores.append(0.0)
        elif key == "gst_number":
            sub_scores.append(1.0 if str(p).strip() == str(t).strip() else 0.0)
        else:
            sub_scores.append(1.0 if abs(float(p) - float(t)) <= 0.01 else 0.0)

    return sum(sub_scores) / len(sub_scores) if sub_scores else 1.0


# ---------- Score all fields for one bill ----------

FIELD_SCORERS = {
    "vendor_name": lambda p, t: score_vendor_name(
        (p or {}).get("vendor_name"), (t or {}).get("vendor_name")
    ),
    "invoice_number": lambda p, t: score_exact(
        (p or {}).get("invoice_number"), (t or {}).get("invoice_number")
    ),
    "date": lambda p, t: score_date(
        (p or {}).get("date"), (t or {}).get("date")
    ),
    "amount": lambda p, t: score_amount(
        (p or {}).get("amount"), (t or {}).get("amount")
    ),
    "currency": lambda p, t: score_exact(
        (p or {}).get("currency"), (t or {}).get("currency")
    ),
    "tax_gst": lambda p, t: score_tax_gst(
        (p or {}).get("tax_gst"), (t or {}).get("tax_gst")
    ),
}


def score_bill(prediction: dict, ground_truth: dict) -> dict[str, float]:
    """Score all fields for a single bill. Returns {field: score}."""
    scores = {}
    for field, scorer in FIELD_SCORERS.items():
        scores[field] = round(scorer(prediction, ground_truth), 4)
    return scores


# ---------- Cost tracking ----------

def estimate_cost(extractor, predictions: list[dict], dataset: str = "handwritten") -> dict:
    """Aggregate cost info from predictions."""
    total_input_tokens = sum(p.get("_input_tokens", 0) for p in predictions)
    total_output_tokens = sum(p.get("_output_tokens", 0) for p in predictions)
    n = len(predictions)

    input_cost = (total_input_tokens / 1_000_000) * extractor.input_price_per_1m
    output_cost = (total_output_tokens / 1_000_000) * extractor.output_price_per_1m
    total_cost = round(input_cost + output_cost, 6)

    return {
        "model": extractor.model_name,
        "dataset": dataset,
        "num_bills": n,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "cost_per_bill": round(total_cost / n, 6) if n > 0 else 0,
        "cost_per_100_bills": round((total_cost / n) * 100, 4) if n > 0 else 0,
        "total_cost": total_cost,
    }


# ---------- Main evaluation runner ----------

def run_evaluation(
    ground_truth_path: str,
    samples_dir: str,
    model_names: list[str] | None = None,
    output_dir: str = "eval/results",
    request_delay: float = 13.0,
    dataset: str = "handwritten",
    save_predictions: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run full evaluation:
    1. Load ground truth
    2. For each model, extract all bills
    3. Score per field per bill
    4. Aggregate accuracy per model per field
    5. Track cost
    6. Save CSV results

    request_delay: seconds to sleep between API calls. The Gemini free tier
    allows ~5 requests/minute (RPM), so a delay of ~13s keeps us under that.
    Defaults to 13.0s; set 0 to disable.

    dataset: label attached to every result row (e.g. "handwritten" or
    "digital") so summaries for different datasets stay separate in the
    merged CSVs.
    """
    if model_names is None:
        model_names = ["gemini-3.1-flash-lite", "gemma-4-31b", "nemotron-nano-12b-vl"]

    with open(ground_truth_path) as f:
        gt_data = json.load(f)

    bills = gt_data["bills"]
    os.makedirs(output_dir, exist_ok=True)

    all_scores = []  # list of dicts for scoring CSV
    cost_rows = []

    for model_name in model_names:
        print(f"\n{'='*60}")
        print(f"Model: {model_name}")
        print(f"{'='*60}")

        extractor = get_extractor(model_name)
        predictions = []

        for bill in bills:
            bill_id = bill["bill_id"]
            image_path = os.path.join(samples_dir, bill["image_file"])
            truth = bill["ground_truth"]

            print(f"  Processing {bill_id} ({bill['image_file']})...")

            if not os.path.exists(image_path):
                print(f"    WARNING: image not found at {image_path}, skipping.")
                continue

            # Extract
            try:
                pred = extractor.extract(image_path)
                predictions.append(pred)
            except Exception as e:
                # On hard failure, record the error but DO NOT score the bill —
                # scoring an empty dict would count as 0 for every field and
                # pollute the per-field accuracy numbers.
                print(f"    ERROR: {e}")
                predictions.append({"_error": str(e)})
                row = {
                    "model": model_name,
                    "bill_id": bill_id,
                    "status": "error",
                    "dataset": dataset,
                    "error": str(e),
                }
                all_scores.append(row)
                continue

            # Respect free-tier rate limits between requests
            import time
            if request_delay > 0:
                time.sleep(request_delay)

            # Score
            scores = score_bill(pred, truth)
            row = {
                "model": model_name,
                "bill_id": bill_id,
                "status": "ok",
                "dataset": dataset,
                **scores,
            }
            all_scores.append(row)
            print(f"    Scores: {scores}")

        # Cost
        if predictions:
            cost_info = estimate_cost(extractor, predictions, dataset=dataset)
            cost_rows.append(cost_info)
            print(f"  Cost: ${cost_info['cost_per_bill']:.6f}/bill")
            print(f"        ${cost_info['cost_per_100_bills']:.4f}/100 bills")

        # Optionally persist raw predictions (needed for the Zoho push step).
        if save_predictions:
            pred_dir = os.path.join(output_dir, "predictions")
            os.makedirs(pred_dir, exist_ok=True)
            ok_predictions = [p for p in predictions if "_error" not in p]
            safe_name = model_name.replace("/", "_").replace(":", "_")
            pred_path = os.path.join(pred_dir, f"{dataset}_{safe_name}.json")
            with open(pred_path, "w", encoding="utf-8") as f:
                json.dump(ok_predictions, f, indent=2, ensure_ascii=False)
            print(f"  Saved {len(ok_predictions)} predictions to {pred_path}")

    # Build accuracy table (per model, per field — average across bills)
    scores_df = pd.DataFrame(all_scores)
    if not scores_df.empty:
        ok_df = scores_df[scores_df.get("status", "ok") == "ok"].copy()
        if ok_df.empty:
            # Every bill errored (e.g. quota exhausted) — nothing to aggregate.
            accuracy_df = pd.DataFrame(columns=["model", "bills_scored"])
        else:
            acc_cols = [
                c for c in ok_df.columns
                if c not in ("model", "bill_id", "status", "error", "dataset")
            ]
            accuracy_df = ok_df.groupby(["model", "dataset"])[acc_cols].mean().reset_index()
            accuracy_df = accuracy_df.round(4)
            # Convert to percentages
            for col in acc_cols:
                accuracy_df[col] = (accuracy_df[col] * 100).round(1)
            # Note how many bills each model successfully processed
            counts = ok_df.groupby(["model", "dataset"]).size().rename("bills_scored")
            accuracy_df = accuracy_df.merge(
                counts,
                left_on=["model", "dataset"],
                right_index=True,
                how="left",
            )
    else:
        accuracy_df = pd.DataFrame()

    cost_df = pd.DataFrame(cost_rows) if cost_rows else pd.DataFrame()

    # Save. Merge with any existing results so multiple partial runs
    # (different models / days) accumulate into the same summary tables.
    def _merge_and_save(df: pd.DataFrame, filename: str, keys: list[str]) -> None:
        path = os.path.join(output_dir, filename)
        if df.empty:
            return
        if os.path.exists(path):
            old = pd.read_csv(path)
            # Existing rows predating the dataset tag are all handwritten.
            if "dataset" in df.columns and "dataset" not in old.columns:
                old["dataset"] = "handwritten"
            combined = pd.concat([old, df], ignore_index=True)
            if "status" in combined.columns:
                # Successful extractions must win over transient error rows
                # recorded in earlier partial runs.
                combined["_ok"] = combined["status"].astype(str) == "ok"
                combined = combined.sort_values("_ok", ascending=False)
                combined = combined.drop(columns="_ok")
                combined = combined.drop_duplicates(subset=keys, keep="first")
            else:
                combined = combined.drop_duplicates(subset=keys, keep="last")
            combined.to_csv(path, index=False)
        else:
            df.to_csv(path, index=False)

    _merge_and_save(
        scores_df, "per_bill_scores.csv", ["model", "bill_id"]
    )
    _merge_and_save(
        accuracy_df, "accuracy_summary.csv", ["model", "dataset"]
    )
    _merge_and_save(cost_df, "cost_summary.csv", ["model", "dataset"])

    if not accuracy_df.empty:
        print(f"\n{'='*60}")
        print("ACCURACY SUMMARY (% per field)")
        print(f"{'='*60}")
        print(accuracy_df.to_string(index=False))

    if not cost_df.empty:
        print(f"\n{'='*60}")
        print("COST SUMMARY")
        print(f"{'='*60}")
        print(cost_df.to_string(index=False))

    return accuracy_df, cost_df


if __name__ == "__main__":
    import sys

    gt_path = sys.argv[1] if len(sys.argv) > 1 else "data/ground_truth/ground_truth.json"
    samples = sys.argv[2] if len(sys.argv) > 2 else "data/samples"
    run_evaluation(gt_path, samples)

