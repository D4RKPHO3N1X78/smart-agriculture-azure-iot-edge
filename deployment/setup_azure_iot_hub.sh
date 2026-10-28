#!/usr/bin/env bash
# ==============================================================================
# Azure IoT Hub & Azure IoT Edge Deployment Automation Script
# Project: Smart Agriculture Edge Irrigation Decision System
# Target Account: ADT23SOCB0882@students.mituniversity.edu.in
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

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-smart-irrigation}"
LOCATION="${LOCATION:-koreacentral}"
IOT_HUB_NAME="${IOT_HUB_NAME:-iothub-smart-irrigation-8921}"
ACR_NAME="${ACR_NAME:-acrirrigation8921}"
EDGE_DEVICE_ID="${EDGE_DEVICE_ID:-irrigation-edge-01}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "\n${BOLD}Active Configuration:${RESET}"
echo -e " - Resource Group:      ${CYAN}${RESOURCE_GROUP}${RESET}"
echo -e " - Azure Region:        ${CYAN}${LOCATION}${RESET}"
echo -e " - Azure IoT Hub:       ${CYAN}${IOT_HUB_NAME}${RESET}"
echo -e " - Container Registry:  ${CYAN}${ACR_NAME}${RESET}"
echo -e " - IoT Edge Device ID:  ${CYAN}${EDGE_DEVICE_ID}${RESET}"

# Deploy modules to edge device
echo -e "\nApplying edge deployment manifest to ${EDGE_DEVICE_ID}..."
az iot edge set-modules \
    --hub-name "${IOT_HUB_NAME}" \
    --device-id "${EDGE_DEVICE_ID}" \
    --content "${PROJECT_ROOT}/deployment/deployment.amd64.json"

DEVICE_CONN_STR=$(az iot hub device-identity connection-string show \
    --hub-name "${IOT_HUB_NAME}" \
    --device-id "${EDGE_DEVICE_ID}" \
    --query connectionString -o tsv)

echo -e "\n${BOLD}${GREEN}======================================================================${RESET}"
echo -e "${BOLD}${GREEN}  SUCCESS: EDGE MODULES DEPLOYED TO IOT HUB!                          ${RESET}"
echo -e "${BOLD}${GREEN}======================================================================${RESET}"
echo -e "\n${BOLD}Edge Device Connection String:${RESET}"
echo -e "${CYAN}${DEVICE_CONN_STR}${RESET}"
