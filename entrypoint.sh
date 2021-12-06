#!/bin/bash
set -e

echo "Running script"
echo -e "$EE_SERVICE_ACCOUNT_JSON" | base64 -d > service_account.json
export GOOGLE_APPLICATION_CREDENTIALS="service_account.json"

exec /opt/conda/envs/env/bin/python main.py
