from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def build_icon(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"Source image not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        rgba = img.convert("RGBA")
        rgba.save(
            destination,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate .ico from source image")
    parser.add_argument("--src", required=True, type=Path, help="Path to source image (jpg/png)")
    parser.add_argument("--out", required=True, type=Path, help="Path to output ico file")
    args = parser.parse_args()
    out = build_icon(args.src, args.out)
    print(out)


if __name__ == "__main__":
    main()

