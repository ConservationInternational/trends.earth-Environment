#!/bin/bash
set -e

echo "Running script"

# Create secure temporary file for service account credentials
CREDENTIALS_FILE=$(mktemp -t service_account_XXXXXX.json)

# Ensure file is only readable by owner
chmod 600 "$CREDENTIALS_FILE"

# Decode and write credentials to secure temporary file
echo -e "$EE_SERVICE_ACCOUNT_JSON" | base64 -d > "$CREDENTIALS_FILE"

# Set environment variable to point to secure credentials file
export GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_FILE"

# Cleanup function to remove credentials file on exit
cleanup() {
    if [ -f "$CREDENTIALS_FILE" ]; then
        # Overwrite file content before deletion for extra security
        dd if=/dev/zero of="$CREDENTIALS_FILE" bs=1024 count=1 2>/dev/null || true
        rm -f "$CREDENTIALS_FILE"
    fi
}

# Set trap to cleanup on any exit
trap cleanup EXIT INT TERM

exec python main.py
