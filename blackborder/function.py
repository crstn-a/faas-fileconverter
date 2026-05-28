# blackborder/function.py — Adds a black border to an image using Pillow.
# This script is designed to run inside an isolated Docker container as a FaaS function.
from PIL import Image, ImageOps
import sys

def process(input_path, output_path):
    # Open the input image file from the specified path
    img = Image.open(input_path)

    # Use PIL ImageOps to add a 30-pixel black border around the original image
    bordered = ImageOps.expand(
        img,
        border=30,
        fill="black"
    )

    # Save the newly bordered image to the specified output path
    bordered.save(output_path)

if __name__ == "__main__":
    # The script reads input and output file paths from the command line arguments
    process(sys.argv[1], sys.argv[2])