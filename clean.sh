#!/usr/bin/env bash

set -euo pipefail

DELETE_PYCACHE=false
DELETE_PYC=false
DELETE_FILE_PATTERN=""

usage() {
    cat <<EOF
Usage:
  $0 [options]

Options:
  --pycache               Remove all __pycache__ directories
  --pyc                   Remove all *.pyc files
  --file <pattern>        Remove files matching pattern
  --all                   Remove __pycache__, *.pyc, and Zone.Identifier files
  -h, --help              Show this help

Examples:
  $0 --pycache
  $0 --file '*:Zone.Identifier'
  $0 --pycache --pyc --file '*.log'
  $0 --all
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pycache)
            DELETE_PYCACHE=true
            shift
            ;;
        --pyc)
            DELETE_PYC=true
            shift
            ;;
        --file)
            DELETE_FILE_PATTERN="$2"
            shift 2
            ;;
        --all)
            DELETE_PYCACHE=true
            DELETE_PYC=true
            DELETE_FILE_PATTERN='*:Zone.Identifier'
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if $DELETE_PYCACHE; then
    echo "Removing __pycache__ directories..."
    find . -type d -name "__pycache__" -exec rm -rf {} +
fi

if $DELETE_PYC; then
    echo "Removing *.pyc files..."
    find . -type f -name "*.pyc" -delete
fi

if [[ -n "$DELETE_FILE_PATTERN" ]]; then
    echo "Removing files matching: $DELETE_FILE_PATTERN"
    find . -type f -name "$DELETE_FILE_PATTERN" -delete
fi

echo "Cleanup completed."
