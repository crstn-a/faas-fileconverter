import sys
import hashlib

def process(input_path, output_path):
    with open(input_path, "rb") as infile:
        data = infile.read()

    sha = hashlib.sha256(data).hexdigest()

    with open(output_path, "w") as outfile:
        outfile.write(sha)

if __name__ == "__main__":
    process(sys.argv[1], sys.argv[2])