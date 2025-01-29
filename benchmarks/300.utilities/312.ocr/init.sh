#!/bin/bash

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

if command_exists apt-get; then
    echo "Using apt package manager"
    apt-get install -y tesseract-ocr

elif command_exists yum; then
    echo "Using yum package manager"
    yum install -y tesseract

elif command_exists apk; then
    echo "Using apk package manager"
    apk add tesseract-ocr

else
    echo "Error: No supported package manager found (apt, yum, or apk)"
    exit 1
fi

echo "tesseract-ocr installation completed"
