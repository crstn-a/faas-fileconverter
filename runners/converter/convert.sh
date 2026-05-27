#!/bin/bash
# convert.sh — runs INSIDE the Docker container
# Arguments:
#   $1 = input file path
#   $2 = output file path
# File type is auto-detected from the input filename extension.

INPUT=$1
OUTPUT=$2

# Detect type from the extension of the input filename
TYPE="${INPUT##*.}"
TYPE=$(echo "$TYPE" | tr '[:upper:]' '[:lower:]')

if [ "$TYPE" = "txt" ] || [ "$TYPE" = "md" ]; then
  # Check if the input file contains non-ASCII characters
  if grep -qP '[^\x00-\x7F]' "$INPUT"; then
    echo "Unicode detected — using xelatex"
    pandoc "$INPUT" -o "$OUTPUT" --pdf-engine=xelatex
  else
    echo "ASCII only — using pdflatex"
    pandoc "$INPUT" -o "$OUTPUT" --pdf-engine=pdflatex
  fi

elif [ "$TYPE" = "jpg" ] || [ "$TYPE" = "jpeg" ] || [ "$TYPE" = "png" ]; then
  convert "$INPUT" "$OUTPUT"

else
  echo "Unsupported file type: $TYPE"
  exit 1
fi
