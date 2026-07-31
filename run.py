"""
BillEval — Multi-Model Bill Extraction & Evaluation Framework

Usage:
    py run.py extract          # Run extraction on all bills
    py run.py evaluate         # Run full evaluation (extract + score)
    py run.py zoho-push PATH   # Push extractions to Zoho Books
    py run.py redact           # Run redaction script
"""

import argparse
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_extract(args):
    """Run extraction on all bills (without evaluation)."""
    from src.evaluator import run_evaluation
    # Run extraction-only by passing a subset of models
    models = args.models.split(",") if args.models else ["gemini-3.1-flash-lite"]
    
    # We use run_evaluation but only care about the predictions
    # A more targeted approach would separate extraction from evaluation
    acc_df, cost_df = run_evaluation(
        ground_truth_path=args.gt,
        samples_dir=args.samples,
        model_names=models,
        output_dir=args.output,
    )
    print("\nDone. Results in", args.output)


def cmd_evaluate(args):
    """Run full evaluation (extract + score + cost)."""
    from src.evaluator import run_evaluation

    models = args.models.split(",") if args.models else [
        "gemini-3.1-flash-lite", "gemma-4-31b", "nemotron-nano-12b-vl"
    ]

    accuracy_df, cost_df = run_evaluation(
        ground_truth_path=args.gt,
        samples_dir=args.samples,
        model_names=models,
        output_dir=args.output,
        request_delay=args.delay,
        dataset=args.dataset,
        save_predictions=args.save_predictions,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if not accuracy_df.empty:
        print("\nAccuracy (% per field):")
        print(accuracy_df.to_string(index=False))

    if not cost_df.empty:
        print("\nCost:")
        print(cost_df.to_string(index=False))


def cmd_zoho_push(args):
    """Push extracted predictions to Zoho Books."""
    from src.zoho_integration import ZohoBooksClient

    client = ZohoBooksClient()
    print(f"Pushing bills from {args.predictions} to Zoho Books...")
    results = client.create_expenses_from_file(
        args.predictions, max_bills=args.max
    )

    created = sum(1 for r in results if r["status"] == "created")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\nDone. {created} created, {failed} failed.")


def cmd_redact(args):
    """Run redaction script."""
    from scripts.redact_images import main as redact_main
    sys.argv = ["redact_images.py"]
    if args.input:
        sys.argv.extend(["--input", args.input])
    if args.output:
        sys.argv.extend(["--output", args.output])
    if args.blur_all:
        sys.argv.append("--blur-all")
    redact_main()


def main():
    parser = argparse.ArgumentParser(
        description="BillEval — Multi-Model Bill Extraction & Evaluation"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # extract
    p_extract = subparsers.add_parser("extract", help="Run extraction only")
    p_extract.add_argument("--models", default="gemini-3.1-flash-lite")
    p_extract.add_argument("--gt", default="data/ground_truth/ground_truth.json")
    p_extract.add_argument("--samples", default="data/samples")
    p_extract.add_argument("--output", default="eval/results")
    p_extract.set_defaults(func=cmd_extract)

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Run full evaluation")
    p_eval.add_argument(
        "--models",
        default="gemini-3.1-flash-lite,gemma-4-31b,nemotron-nano-12b-vl",
        help="Comma-separated model names",
    )
    p_eval.add_argument("--gt", default="data/ground_truth/ground_truth.json")
    p_eval.add_argument("--samples", default="data/samples")
    p_eval.add_argument("--output", default="eval/results")
    p_eval.add_argument(
        "--dataset",
        default="handwritten",
        help='Dataset label for results (e.g. "handwritten" or "digital")',
    )
    p_eval.add_argument(
        "--save-predictions",
        action="store_true",
        help="Also save raw per-model predictions to eval/results/predictions/",
    )
    p_eval.add_argument(
        "--delay",
        type=float,
        default=13.0,
        help="Seconds to sleep between API calls (free-tier rate limit)",
    )
    p_eval.set_defaults(func=cmd_evaluate)

    # zoho-push
    p_zoho = subparsers.add_parser("zoho-push", help="Push to Zoho Books")
    p_zoho.add_argument("predictions", help="Path to extractions JSON file")
    p_zoho.add_argument("--max", type=int, default=None)
    p_zoho.set_defaults(func=cmd_zoho_push)

    # redact
    p_redact = subparsers.add_parser("redact", help="Redact bill images")
    p_redact.add_argument("--input", default="raw_photos")
    p_redact.add_argument("--output", default="data/samples")
    p_redact.add_argument("--blur-all", action="store_true")
    p_redact.set_defaults(func=cmd_redact)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()


