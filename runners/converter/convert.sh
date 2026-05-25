#!/bin/bash
# convert.sh — runs INSIDE the Docker container
# Arguments:
#   $1 = input file path
#   $2 = output file path
#   $3 = input file type (txt, md, jpg, png)

INPUT=$1
OUTPUT=$2
TYPE=$3

if [ "$TYPE" = "txt" ] || [ "$TYPE" = "md" ]; then
  # Check if the input file contains non‑ASCII characters
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
