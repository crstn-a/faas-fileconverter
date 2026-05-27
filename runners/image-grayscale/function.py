#!/usr/bin/env python3
"""
FaaS Built-in Function: image-grayscale
Converts a color image to grayscale.
Usage: python function.py <input_path> <output_path>
"""

import sys
from PIL import Image


def process(input_path: str, output_path: str):
    img = Image.open(input_path).convert("L")
    img.save(output_path)
    print(f"[grayscale] {input_path} -> {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: function.py <input> <output>", file=sys.stderr)
        sys.exit(1)
    process(sys.argv[1], sys.argv[2])
