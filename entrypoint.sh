#!/bin/bash
set -e

echo "Running script"

# Define credentials file path
CREDENTIALS_FILE="/project/service_account.json"

# Decode and write credentials to the file
echo "$EE_SERVICE_ACCOUNT_JSON" | base64 -d > "$CREDENTIALS_FILE"

# Set permissions
chmod 600 "$CREDENTIALS_FILE"

# Set environment variable for GEE
export GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_FILE"

# Cleanup function to remove credentials file on exit
cleanup() {
    echo "Cleaning up credentials file..."
    if [ -f "$CREDENTIALS_FILE" ]; then
        # Overwrite file content before deletion for extra security
        # Using shred if available, otherwise dd
        if command -v shred &> /dev/null; then
            shred -u "$CREDENTIALS_FILE"
        else
            dd if=/dev/zero of="$CREDENTIALS_FILE" bs=1024 count=1 2>/dev/null || true
            rm -f "$CREDENTIALS_FILE"
        fi
    fi
}

# Set trap to cleanup on any exit
trap cleanup EXIT INT TERM

exec python main.py
