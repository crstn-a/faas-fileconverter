# text-uppercase/function.py — Converts text in a file to uppercase.
# This script is designed to run inside an isolated Docker container as a FaaS function.
import sys

def process(input_path, output_path):
    # Open and read the entire contents of the input file
    with open(input_path, "r") as infile:
        text = infile.read()

    # Convert the read text to uppercase
    upper = text.upper()

    # Write the uppercase text to the specified output file path
    with open(output_path, "w") as outfile:
        outfile.write(upper)

if __name__ == "__main__":
    # The script reads input and output file paths from the command line arguments
    process(sys.argv[1], sys.argv[2])