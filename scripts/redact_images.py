"""
Step 2: PII Redaction Utility

Blurs sensitive regions in bill images before sending to external APIs.
Usage:
    py scripts/redact_images.py --input path/to/raw_photos/ --output data/samples/

You can also specify manual regions or use a simple full-image blur approach.
For handwritten bills, the safest approach is:
  1. Take photos
  2. Open each in any image viewer
  3. Note pixel regions (x, y, w, h) containing phone numbers, full names, account numbers
  4. Run this script to blur those regions
"""

import argparse
import os
from pathlib import Path
from PIL import Image, ImageFilter


def blur_regions(
    image_path: Path,
    output_path: Path,
    regions: list[tuple[int, int, int, int]] | None = None,
    blur_radius: int = 30,
):
    """
    Open an image, blur specified rectangular regions, save result.

    Each region is (x, y, width, height) in pixels.
    If regions is None, the image is saved unmodified (pass-through).
    """
    img = Image.open(image_path).convert("RGB")
    if regions:
        for x, y, w, h in regions:
            crop = img.crop((x, y, x + w, y + h))
            blurred = crop.filter(ImageFilter.GaussianBlur(blur_radius))
            img.paste(blurred, (x, y))
    img.save(output_path)
    print(f"  Saved: {output_path.name}")


def process_directory(
    input_dir: Path, output_dir: Path, blur_all: bool = False
):
    """Process all images in input_dir, optionally blurring the entire image."""
    os.makedirs(output_dir, exist_ok=True)
    image_exts = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

    for fname in os.listdir(input_dir):
        ext = Path(fname).suffix.lower()
        if ext not in image_exts:
            continue
        in_path = input_dir / fname
        out_path = output_dir / fname

        if blur_all:
            # Blur the entire image (heavy-handed but safe for testing)
            img = Image.open(in_path).convert("RGB")
            img = img.filter(ImageFilter.GaussianBlur(25))
            img.save(out_path)
            print(f"  Full-blur saved: {out_path.name}")
        else:
            # Pass-through: you'll manually add region coordinates
            blur_regions(in_path, out_path, regions=None)


def main():
    parser = argparse.ArgumentParser(
        description="Redact sensitive info from bill images."
    )
    parser.add_argument(
        "--input",
        default="raw_photos",
        help="Directory containing original photos (default: raw_photos/)",
    )
    parser.add_argument(
        "--output",
        default="data/samples",
        help="Output directory for redacted images (default: data/samples/)",
    )
    parser.add_argument(
        "--blur-all",
        action="store_true",
        help="Blur entire image (quick but may affect extraction quality).",
    )
    parser.add_argument(
        "--region",
        nargs=4,
        type=int,
        metavar=("X", "Y", "W", "H"),
        action="append",
        help="Region to blur: --region x y w h (repeatable)",
    )
    parser.add_argument(
        "--image",
        type=str,
        help="Process a single image file instead of a directory.",
    )
    args = parser.parse_args()

    if args.image:
        in_path = Path(args.image)
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / in_path.name
        blur_regions(in_path, out_path, regions=args.region)
    else:
        process_directory(
            Path(args.input),
            Path(args.output),
            blur_all=args.blur_all,
        )

    print("Done.")


if __name__ == "__main__":
    main()
