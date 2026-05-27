#!/usr/bin/env python3
"""
FaaS Built-in Function: image-resize
Resizes an image to specified dimensions via env vars.
Usage: python function.py <input_path> <output_path>
Env:   RESIZE_WIDTH (default 800), RESIZE_HEIGHT (default 600)
"""

import sys
import os
from PIL import Image


def process(input_path: str, output_path: str, width: int = 800, height: int = 600):
    img     = Image.open(input_path)
    resized = img.resize((width, height), Image.LANCZOS)
    resized.save(output_path)
    print(f"[resize] {width}x{height} -> {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: function.py <input> <output>", file=sys.stderr)
        sys.exit(1)
    w = int(os.environ.get("RESIZE_WIDTH",  800))
    h = int(os.environ.get("RESIZE_HEIGHT", 600))
    process(sys.argv[1], sys.argv[2], w, h)
