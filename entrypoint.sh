#!/bin/bash
set -e

echo "Running script"

# Check for OAuth credentials first
if [ -n "$GEE_OAUTH_ACCESS_TOKEN" ] && [ -n "$GEE_OAUTH_REFRESH_TOKEN" ]; then
    echo "Using OAuth credentials for GEE authentication"
    
    # Validate required OAuth environment variables
    if [ -z "$GOOGLE_OAUTH_CLIENT_ID" ] || [ -z "$GOOGLE_OAUTH_CLIENT_SECRET" ]; then
        echo "ERROR: OAuth credentials provided but missing GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET"
        exit 1
    fi
    
    echo "OAuth environment variables validated successfully"
    
elif [ -n "$EE_SERVICE_ACCOUNT_JSON" ]; then
    echo "Using service account for GEE authentication"
    
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
    
else
    echo "ERROR: No GEE credentials provided"
    echo "Please provide either:"
    echo "  - OAuth tokens: GEE_OAUTH_ACCESS_TOKEN, GEE_OAUTH_REFRESH_TOKEN, GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET"
    echo "  - Service account: EE_SERVICE_ACCOUNT_JSON (base64 encoded)"
    exit 1
fi

exec python main.py
