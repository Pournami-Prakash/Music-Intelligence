#!/bin/bash
# Run once to create VCN + public subnet for the Atlas instance.
# Usage: bash deploy/oci_setup_network.sh <compartment_ocid>
set -euo pipefail

COMPARTMENT_ID="${1:?Usage: $0 <compartment_ocid>}"

echo "Creating VCN..."
VCN_ID=$(oci network vcn create \
  --compartment-id "$COMPARTMENT_ID" \
  --cidr-block "10.0.0.0/16" \
  --display-name "atlas-vcn" \
  --wait-for-state AVAILABLE \
  --query 'data.id' --raw-output)
echo "VCN: $VCN_ID"

echo "Creating internet gateway..."
IGW_ID=$(oci network internet-gateway create \
  --compartment-id "$COMPARTMENT_ID" \
  --vcn-id "$VCN_ID" \
  --is-enabled true \
  --display-name "atlas-igw" \
  --wait-for-state AVAILABLE \
  --query 'data.id' --raw-output)
echo "IGW: $IGW_ID"

echo "Adding default route to internet gateway..."
RT_ID=$(oci network route-table list \
  --compartment-id "$COMPARTMENT_ID" \
  --vcn-id "$VCN_ID" \
  --query 'data[0].id' --raw-output)
oci network route-table update \
  --rt-id "$RT_ID" \
  --route-rules "[{\"networkEntityId\": \"$IGW_ID\", \"destination\": \"0.0.0.0/0\", \"destinationType\": \"CIDR_BLOCK\"}]" \
  --force --wait-for-state AVAILABLE > /dev/null
echo "Route table updated."

echo "Creating public subnet..."
SUBNET_ID=$(oci network subnet create \
  --compartment-id "$COMPARTMENT_ID" \
  --vcn-id "$VCN_ID" \
  --cidr-block "10.0.0.0/24" \
  --display-name "atlas-subnet" \
  --route-table-id "$RT_ID" \
  --prohibit-public-ip-on-vnic false \
  --wait-for-state AVAILABLE \
  --query 'data.id' --raw-output)
echo "Subnet: $SUBNET_ID"

echo ""
echo "Network ready. Save these for the next script:"
echo "  COMPARTMENT_ID=$COMPARTMENT_ID"
echo "  SUBNET_ID=$SUBNET_ID"
