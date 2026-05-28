# qrcode/function.py — Generates a QR code from text input.
# This script is designed to run inside an isolated Docker container as a FaaS function.
import qrcode
import sys

def process(input_path, output_path):
    # Read text from uploaded file containing the text to encode
    with open(input_path, "r") as infile:
        text = infile.read().strip()

    # Generate QR code image using the qrcode library
    img = qrcode.make(text)

    # Save QR image to the specified output file path
    img.save(output_path)

if __name__ == "__main__":
    # The script reads input and output file paths from the command line arguments
    process(sys.argv[1], sys.argv[2])