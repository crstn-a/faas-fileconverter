#!/bin/bash
# convert.sh — runs INSIDE the Docker container
# This is the entrypoint script for the builtin 'convert-to-pdf' function.
# Arguments:
#   $1 = input file path
#   $2 = output file path
# File type is auto-detected from the input filename extension.

INPUT=$1
OUTPUT=$2

# Detect type from the extension of the input filename
# Extract the extension after the last dot
TYPE="${INPUT##*.}"
# Convert the extension to lowercase for case-insensitive matching
TYPE=$(echo "$TYPE" | tr '[:upper:]' '[:lower:]')

# If the file is a text or markdown document
if [ "$TYPE" = "txt" ] || [ "$TYPE" = "md" ]; then
  # Check if the input file contains non-ASCII characters to choose the right PDF engine
  if grep -qP '[^\x00-\x7F]' "$INPUT"; then
    echo "Unicode detected — using xelatex"
    # Use pandoc with xelatex engine for Unicode support
    pandoc "$INPUT" -o "$OUTPUT" --pdf-engine=xelatex
  else
    echo "ASCII only — using pdflatex"
    # Use pandoc with standard pdflatex engine
    pandoc "$INPUT" -o "$OUTPUT" --pdf-engine=pdflatex
  fi

# If the file is an image
elif [ "$TYPE" = "jpg" ] || [ "$TYPE" = "jpeg" ] || [ "$TYPE" = "png" ]; then
  # Use ImageMagick's convert tool to transform the image to PDF
  convert "$INPUT" "$OUTPUT"

else
  # If the file type is not supported, print an error and exit with a failure code
  echo "Unsupported file type: $TYPE"
  exit 1
fi
