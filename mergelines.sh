#!/usr/bin/env bash

FILE="$1"

if [ -z "$FILE" ]; then
    echo "Usage: $0 <file>"
    exit 1
fi

awk '
{
    if ($0 ~ /^[[:space:]]*$/) {
        blank++
        if (blank <= 1) print
    } else {
        blank=0
        print
    }
}
' "$FILE" > "${FILE}.tmp" && mv "${FILE}.tmp" "$FILE"

echo "Normalized blank lines in $FILE"
