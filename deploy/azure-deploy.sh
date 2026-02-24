#!/usr/bin/env bash
# Prevent Git Bash on Windows from converting /app/src → C:/Program Files/Git/app/src
export MSYS_NO_PATHCONV=1
# ---------------------------------------------------------------------------
# Azure deployment script for Solar Sweden MCP
# Deploys to Azure Container Apps (scale-to-zero, external ingress)
#
# Prerequisites:
#   - Azure CLI installed and logged in (`az login`)
#   - Docker installed (for local build verification)
#
# Usage:
#   chmod +x deploy/azure-deploy.sh
#   ./deploy/azure-deploy.sh
#
# Or override defaults:
#   RESOURCE_GROUP=my-rg LOCATION=swedencentral ./deploy/azure-deploy.sh
# ---------------------------------------------------------------------------
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — edit these or override via environment variables
# ---------------------------------------------------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-solar-mcp-rg}"
LOCATION="${LOCATION:-swedencentral}"
ACR_NAME="${ACR_NAME:-solarmcpacr}"          # Must be globally unique, lowercase
APP_NAME="${APP_NAME:-solar-mcp}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_ENV="${CONTAINER_ENV:-solar-mcp-env}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"            # 0 = scale-to-zero; set 1 to avoid cold start on demo day
MAX_REPLICAS="${MAX_REPLICAS:-3}"
CPU="${CPU:-0.5}"
MEMORY="${MEMORY:-1.0Gi}"

IMAGE_FULL="${ACR_NAME}.azurecr.io/${APP_NAME}:${IMAGE_TAG}"

echo "============================================================"
echo " Solar Sweden MCP — Azure Deployment"
echo "============================================================"
echo " Resource Group : ${RESOURCE_GROUP}"
echo " Location       : ${LOCATION}"
echo " ACR            : ${ACR_NAME}"
echo " App Name       : ${APP_NAME}"
echo " Image          : ${IMAGE_FULL}"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Create resource group
# ---------------------------------------------------------------------------
echo "[1/6] Creating resource group..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none
echo "      OK"

# ---------------------------------------------------------------------------
# Step 2: Create Azure Container Registry
# ---------------------------------------------------------------------------
echo "[2/6] Creating Azure Container Registry..."
az acr create \
  --name "${ACR_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --sku Basic \
  --admin-enabled true \
  --output none
echo "      OK"

# ---------------------------------------------------------------------------
# Step 3: Build & push image using ACR Tasks (no local Docker required)
# ---------------------------------------------------------------------------
echo "[3/6] Building and pushing Docker image via ACR Tasks..."
# Run from repo root (one level up from deploy/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

az acr build \
  --registry "${ACR_NAME}" \
  --image "${APP_NAME}:${IMAGE_TAG}" \
  --file "${REPO_ROOT}/Dockerfile" \
  "${REPO_ROOT}"
echo "      OK — image: ${IMAGE_FULL}"

# ---------------------------------------------------------------------------
# Step 4: Create Container Apps environment
# ---------------------------------------------------------------------------
echo "[4/6] Creating Container Apps environment..."
az containerapp env create \
  --name "${CONTAINER_ENV}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none
echo "      OK"

# ---------------------------------------------------------------------------
# Step 5: Deploy the container app
# ---------------------------------------------------------------------------
echo "[5/6] Deploying Container App..."

# Get ACR credentials
ACR_SERVER="${ACR_NAME}.azurecr.io"
ACR_USERNAME=$(az acr credential show --name "${ACR_NAME}" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "${ACR_NAME}" --query "passwords[0].value" -o tsv)

az containerapp create \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --environment "${CONTAINER_ENV}" \
  --image "${IMAGE_FULL}" \
  --registry-server "${ACR_SERVER}" \
  --registry-username "${ACR_USERNAME}" \
  --registry-password "${ACR_PASSWORD}" \
  --ingress external \
  --target-port 8000 \
  --min-replicas "${MIN_REPLICAS}" \
  --max-replicas "${MAX_REPLICAS}" \
  --cpu "${CPU}" \
  --memory "${MEMORY}" \
  --env-vars \
      PYTHONIOENCODING=utf-8 \
      LANG=C.UTF-8 \
      PYTHONPATH=/app/src \
  --output none
echo "      OK"

# ---------------------------------------------------------------------------
# Step 6: Print the public URL
# ---------------------------------------------------------------------------
echo "[6/6] Retrieving public URL..."
APP_URL=$(az containerapp show \
  --name "${APP_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo ""
echo "============================================================"
echo " DEPLOYMENT COMPLETE"
echo "============================================================"
echo " App URL       : https://${APP_URL}"
echo " Health check  : https://${APP_URL}/health"
echo " MCP SSE       : https://${APP_URL}/sse"
echo " MCP HTTP      : https://${APP_URL}/messages"
echo ""
echo " Next: Register https://${APP_URL}/sse as an MCP action in Copilot Studio."
echo "============================================================"
