#!/bin/bash

DIR=$1
VERBOSE=$2

CHROMIUM_URL="https://storage.googleapis.com/chrome-for-testing-public/127.0.6533.88/linux64/chrome-linux64.zip"

# Define the script directory and the download path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
DOWNLOAD_DIR="${DIR}/chromium"

# Create the target directory if it doesn't exist
mkdir -p "$DOWNLOAD_DIR"

# Download Chromium
curl -o "${DOWNLOAD_DIR}/chrome-linux.zip" "$CHROMIUM_URL"

# Extract the downloaded zip file
unzip -q "${DOWNLOAD_DIR}/chrome-linux.zip" -d "$DOWNLOAD_DIR"

# Clean up the downloaded zip file
rm "${DOWNLOAD_DIR}/chrome-linux.zip"

# Move the extracted files to the final directory
mv "${DOWNLOAD_DIR}/chrome-linux"/* "${DOWNLOAD_DIR}/"

# Remove the empty directory
rmdir "${DOWNLOAD_DIR}/chrome-linux"

