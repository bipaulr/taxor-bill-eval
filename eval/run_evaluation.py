"""
Run full evaluation pipeline from the command line.

Usage:
    py eval\run_evaluation.py

Optional:
    py eval\run_evaluation.py --models gemini-2.5-flash,gpt-4o
    py eval\run_evaluation.py --gt data/ground_truth/ground_truth.json --samples data/samples/
"""

import argparse
import sys
import os

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.evaluator import run_evaluation


def main():
    parser = argparse.ArgumentParser(
        description="Run multi-model bill extraction evaluation."
    )
    parser.add_argument(
        "--models",
        default="gemini-3.1-flash-lite,gpt-4o,claude-sonnet-4-6",
        help="Comma-separated list of model names to evaluate",
    )
    parser.add_argument(
        "--gt",
        default="data/ground_truth/ground_truth.json",
        help="Path to ground truth JSON file",
    )
    parser.add_argument(
        "--samples",
        default="data/samples",
        help="Directory containing bill images",
    )
    parser.add_argument(
        "--output",
        default="eval/results",
        help="Directory to write result CSVs",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=13.0,
        help="Seconds to sleep between API calls (free-tier rate limit). Set 0 to disable.",
    )
    args = parser.parse_args()

    model_names = [m.strip() for m in args.models.split(",")]

    print("=" * 60)
    print("BILL EVAL — Multi-Model Extraction Evaluation")
    print("=" * 60)
    print(f"Models:          {model_names}")
    print(f"Ground truth:    {args.gt}")
    print(f"Samples dir:     {args.samples}")
    print(f"Output dir:      {args.output}")
    print(f"Request delay:   {args.delay}s")
    print("=" * 60)

    accuracy_df, cost_df = run_evaluation(
        ground_truth_path=args.gt,
        samples_dir=args.samples,
        model_names=model_names,
        output_dir=args.output,
        request_delay=args.delay,
    )

    print(f"\nResults saved to {args.output}/")
    print("  - per_bill_scores.csv")
    print("  - accuracy_summary.csv")
    print("  - cost_summary.csv")


if __name__ == "__main__":
    main()


