#!/usr/bin/env bash
# ==============================================================================
# Azure IoT Hub & Azure IoT Edge Deployment Automation Script
# Project: Smart Agriculture Edge Irrigation Decision System
# ==============================================================================

set -euo pipefail

# Text formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${BOLD}${CYAN}======================================================================${RESET}"
echo -e "${BOLD}${CYAN}     AZURE IOT HUB & EDGE MODULE AUTOMATED DEPLOYMENT SETUP          ${RESET}"
echo -e "${BOLD}${CYAN}======================================================================${RESET}"

# Default parameters (override by setting environment variables prior to running)
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-smart-agri-edge}"
LOCATION="${LOCATION:-eastus}"
RANDOM_SUFFIX=$((1000 + RANDOM % 9000))
IOT_HUB_NAME="${IOT_HUB_NAME:-iothub-agritech-${RANDOM_SUFFIX}}"
ACR_NAME="${ACR_NAME:-acragritech${RANDOM_SUFFIX}}"
EDGE_DEVICE_ID="${EDGE_DEVICE_ID:-farm-edge-gateway-01}"
IMAGE_TAG="smart-irrigation-module:1.0.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "\n${BOLD}Deployment Configuration:${RESET}"
echo -e " - Resource Group:      ${CYAN}${RESOURCE_GROUP}${RESET}"
echo -e " - Azure Region:        ${CYAN}${LOCATION}${RESET}"
echo -e " - Azure IoT Hub:       ${CYAN}${IOT_HUB_NAME}${RESET}"
echo -e " - Container Registry:  ${CYAN}${ACR_NAME}${RESET}"
echo -e " - IoT Edge Device ID:  ${CYAN}${EDGE_DEVICE_ID}${RESET}"
echo -e " - Project Directory:   ${CYAN}${PROJECT_ROOT}${RESET}"

# 1. Verify Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}[ERROR] Azure CLI ('az') is not installed. Please install it first: https://aka.ms/azure-cli${RESET}"
    exit 1
fi

# 2. Check Azure Login
echo -e "\n${YELLOW}[Step 1/7] Checking Azure Authentication...${RESET}"
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Please log in to your Azure account in the browser:${RESET}"
    az login --output none
fi
ACCOUNT_NAME=$(az account show --query name -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
echo -e "${GREEN}Logged in to Subscription: ${ACCOUNT_NAME} (${SUBSCRIPTION_ID})${RESET}"

# 3. Ensure IoT Extension
echo -e "\n${YELLOW}[Step 2/7] Installing / Updating 'azure-iot' extension...${RESET}"
az extension add --name azure-iot --yes --upgrade &> /dev/null || true
echo -e "${GREEN}azure-iot extension ready.${RESET}"

# 4. Create Resource Group
echo -e "\n${YELLOW}[Step 3/7] Creating Resource Group '${RESOURCE_GROUP}'...${RESET}"
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --output table

# 5. Create Azure IoT Hub
echo -e "\n${YELLOW}[Step 4/7] Creating Azure IoT Hub '${IOT_HUB_NAME}' (Standard S1)...${RESET}"
az iot hub create \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${IOT_HUB_NAME}" \
    --sku S1 \
    --partition-count 2 \
    --output table

# 6. Create Azure Container Registry (ACR) & Build Image in Cloud
echo -e "\n${YELLOW}[Step 5/7] Creating Azure Container Registry '${ACR_NAME}'...${RESET}"
az acr create \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${ACR_NAME}" \
    --sku Basic \
    --admin-enabled true \
    --output table

ACR_LOGIN_SERVER=$(az acr show --name "${ACR_NAME}" --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show --name "${ACR_NAME}" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name "${ACR_NAME}" --query "passwords[0].value" -o tsv)

echo -e "\nBuilding Edge Module Container Image directly in ACR (Cloud Build)..."
az acr build \
    --registry "${ACR_NAME}" \
    --image "${IMAGE_TAG}" \
    --file "${PROJECT_ROOT}/edge_module/Dockerfile" \
    "${PROJECT_ROOT}/edge_module"

# 7. Register IoT Edge Device
echo -e "\n${YELLOW}[Step 6/7] Registering IoT Edge Device '${EDGE_DEVICE_ID}' in IoT Hub...${RESET}"
az iot hub device-identity create \
    --hub-name "${IOT_HUB_NAME}" \
    --device-id "${EDGE_DEVICE_ID}" \
    --edge-enabled \
    --output table

DEVICE_CONN_STR=$(az iot hub device-identity connection-string show \
    --hub-name "${IOT_HUB_NAME}" \
    --device-id "${EDGE_DEVICE_ID}" \
    --query connectionString -o tsv)

# 8. Render and Deploy Deployment Manifest
echo -e "\n${YELLOW}[Step 7/7] Generating concrete deployment manifest and deploying to Edge device...${RESET}"
DEPLOYMENT_AMD64="${PROJECT_ROOT}/deployment/deployment.amd64.json"

sed \
    -e "s|\$CONTAINER_REGISTRY_SERVER|${ACR_LOGIN_SERVER}|g" \
    -e "s|\$CONTAINER_REGISTRY_USERNAME|${ACR_USERNAME}|g" \
    -e "s|\$CONTAINER_REGISTRY_PASSWORD|${ACR_PASSWORD}|g" \
    "${PROJECT_ROOT}/deployment/deployment.template.json" > "${DEPLOYMENT_AMD64}"

az iot edge set-modules \
    --hub-name "${IOT_HUB_NAME}" \
    --device-id "${EDGE_DEVICE_ID}" \
    --content "${DEPLOYMENT_AMD64}"

echo -e "\n${BOLD}${GREEN}======================================================================${RESET}"
echo -e "${BOLD}${GREEN}       DEPLOYMENT COMPLETE! SMART AGRICULTURE EDGE MODULE LIVE        ${RESET}"
echo -e "${BOLD}${GREEN}======================================================================${RESET}"
echo -e "\n${BOLD}Edge Gateway Connection String:${RESET}"
echo -e "${CYAN}${DEVICE_CONN_STR}${RESET}"
echo -e "\n${BOLD}To provision your physical Raspberry Pi / Edge Gateway, edit /etc/aziot/config.toml:${RESET}"
echo -e "  provisioning:"
echo -e "    source = \"manual\""
echo -e "    connection_string = \"${DEVICE_CONN_STR}\""
echo -e "  Then run: ${BOLD}sudo iotedge config apply${RESET}"
echo -e "\n${BOLD}To monitor real-time decision telemetry reaching Azure IoT Hub in the cloud:${RESET}"
echo -e "  ${BOLD}az iot hub monitor-events --hub-name ${IOT_HUB_NAME} --device-id ${EDGE_DEVICE_ID}${RESET}"
echo -e "======================================================================"
