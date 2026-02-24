#!/usr/bin/env bash
# Prevent Git Bash on Windows from converting /app/src → C:/Program Files/Git/app/src
export MSYS_NO_PATHCONV=1
# Rebuild and redeploy to an existing Container App (faster than full deploy).
# Run after code changes.
#
# Usage:  ./deploy/azure-update.sh
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-solar-mcp-rg}"
ACR_NAME="${ACR_NAME:-solarmcpacr}"
APP_NAME="${APP_NAME:-solar-mcp}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "Rebuilding image..."
az acr build \
  --registry "${ACR_NAME}" \
  --image "${APP_NAME}:${IMAGE_TAG}" \
  --file "${REPO_ROOT}/Dockerfile" \
  "${REPO_ROOT}"

echo "Updating Container App..."
az containerapp update \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --image "${ACR_NAME}.azurecr.io/${APP_NAME}:${IMAGE_TAG}" \
  --output none

echo "Done. Checking revision..."
az containerapp revision list \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query "[0].{name:name,state:properties.runningState,created:properties.createdTime}" \
  --output table
