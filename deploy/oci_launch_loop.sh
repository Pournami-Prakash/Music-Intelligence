#!/bin/bash
# Retry loop to claim an A1 Free Tier instance.
# Rotates across all 3 Chicago ADs. Stops on first success.
#
# Shape is 2 OCPU / 12 GB: Oracle halved the Always Free A1 allowance from
# 4 OCPU / 24 GB on 2026-06-15 without announcing it. Asking for the old 4/24
# returns LimitExceeded, which the retry branch below treats as a capacity miss
# — so an over-quota request loops forever and reads like "region is full".
# Always Free instances must be launched in the tenancy's HOME region.
#
# To check capacity without attempting a launch (read-only, much cheaper):
#   oci compute compute-capacity-report create --compartment-id <ocid> \
#     --availability-domain <ad> \
#     --shape-availabilities '[{"instanceShape":"VM.Standard.A1.Flex","instanceShapeConfig":{"ocpus":2,"memoryInGBs":12}}]'
#
# Usage:
#   bash deploy/oci_launch_loop.sh <compartment_ocid> <subnet_ocid>
#
# Get COMPARTMENT_ID from: Profile → Tenancy → OCID
# Get SUBNET_ID from the output of oci_setup_network.sh
set -euo pipefail
export SUPPRESS_LABEL_WARNING=True

COMPARTMENT_ID="${1:?Usage: $0 <compartment_ocid> <subnet_ocid>}"
SUBNET_ID="${2:?Usage: $0 <compartment_ocid> <subnet_ocid>}"
SSH_KEY_FILE="$HOME/.ssh/oracle_atlas.pub"

if [[ ! -f "$SSH_KEY_FILE" ]]; then
  echo "ERROR: SSH public key not found at $SSH_KEY_FILE"
  echo "Run: ssh-keygen -t ed25519 -f ~/.ssh/oracle_atlas -N \"\""
  exit 1
fi

# Get Ubuntu 22.04 Minimal aarch64 image OCID for Chicago
echo "Looking up Ubuntu 22.04 Minimal aarch64 image..."
IMAGE_ID=$(oci compute image list \
  --compartment-id "$COMPARTMENT_ID" \
  --operating-system "Canonical Ubuntu" \
  --operating-system-version "22.04 Minimal aarch64" \
  --shape "VM.Standard.A1.Flex" \
  --sort-by TIMECREATED \
  --sort-order DESC \
  --query 'data[0].id' --raw-output)

if [[ -z "$IMAGE_ID" || "$IMAGE_ID" == "null" ]]; then
  echo "ERROR: Could not find Ubuntu 22.04 Minimal aarch64 image."
  echo "List available images with:"
  echo "  oci compute image list --compartment-id $COMPARTMENT_ID --operating-system 'Canonical Ubuntu' --output table"
  exit 1
fi
echo "Image: $IMAGE_ID"

# Get AD names for this tenancy (format: dpTm:US-CHICAGO-1-AD-1 etc.)
ADS=()
while IFS= read -r ad; do
  [[ -n "$ad" ]] && ADS+=("$ad")
done < <(oci iam availability-domain list \
  --compartment-id "$COMPARTMENT_ID" \
  --query 'data[*].name' --raw-output | tr ',' '\n' | tr -d '[]" ')

echo "Availability domains: ${ADS[*]}"
echo ""
echo "Starting retry loop. Press Ctrl+C to stop."
echo "---"

AD_INDEX=0
ATTEMPT=0

while true; do
  ATTEMPT=$((ATTEMPT + 1))
  AD="${ADS[$((AD_INDEX % ${#ADS[@]}))]}"
  AD_INDEX=$((AD_INDEX + 1))

  echo "[$(date '+%H:%M:%S')] Attempt $ATTEMPT — AD: $AD"

  OUTPUT=$(oci compute instance launch \
    --compartment-id "$COMPARTMENT_ID" \
    --availability-domain "$AD" \
    --shape "VM.Standard.A1.Flex" \
    --shape-config '{"ocpus": 2, "memoryInGBs": 12}' \
    --image-id "$IMAGE_ID" \
    --subnet-id "$SUBNET_ID" \
    --assign-public-ip true \
    --ssh-authorized-keys-file "$SSH_KEY_FILE" \
    --display-name "music-atlas" \
    --boot-volume-size-in-gbs 50 \
    2>&1) || true

  if echo "$OUTPUT" | grep -q '"lifecycle-state"'; then
    echo ""
    echo "SUCCESS! Instance launched."
    INSTANCE_ID=$(echo "$OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['data']['id'])")
    echo "Instance OCID: $INSTANCE_ID"
    echo ""
    echo "Waiting for public IP (may take 60s)..."
    sleep 30
    PUBLIC_IP=$(oci compute instance list-vnics \
      --instance-id "$INSTANCE_ID" \
      --query 'data[0]."public-ip"' --raw-output 2>/dev/null || echo "check console")
    echo "Public IP: $PUBLIC_IP"
    echo ""
    echo "SSH with: ssh -i ~/.ssh/oracle_atlas ubuntu@$PUBLIC_IP"
    break
  elif echo "$OUTPUT" | grep -qi "out of capacity\|LimitExceeded\|Out of host capacity\|InternalError"; then
    echo "  Out of capacity — retrying in 60s..."
    sleep 60
  else
    echo "  Unexpected response:"
    echo "$OUTPUT" | head -5
    echo "  Retrying in 60s..."
    sleep 60
  fi
done
