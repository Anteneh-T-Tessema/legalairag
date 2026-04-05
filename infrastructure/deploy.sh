#!/bin/bash
# Deploy IndyLeg infrastructure to AWS using CDK.
#
# Usage:
#   ./deploy.sh [dev|staging|prod]
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Node.js + npm installed
#   - CDK CLI: npm install -g aws-cdk

set -euo pipefail

ENV="${1:-dev}"
CDK_DIR="$(cd "$(dirname "$0")/cdk" && pwd)"

echo "=== Deploying IndyLeg (env: ${ENV}) ==="

cd "$CDK_DIR"

# Install CDK dependencies
pip install -q aws-cdk-lib constructs

# Bootstrap (first time only — idempotent)
cdk bootstrap --context env="${ENV}" 2>/dev/null || true

# Synthesize (validates templates)
echo "--- Synthesizing CloudFormation templates ---"
cdk synth --context env="${ENV}" --quiet

# Deploy all stacks
echo "--- Deploying stacks ---"
cdk deploy --all \
  --context env="${ENV}" \
  --require-approval broadening \
  --outputs-file "outputs-${ENV}.json"

echo "=== Deployment complete ==="
echo "Outputs saved to: ${CDK_DIR}/outputs-${ENV}.json"

# Print the API URL
if command -v jq &>/dev/null && [[ -f "outputs-${ENV}.json" ]]; then
  API_URL=$(jq -r ".[\"IndyLeg-Api-${ENV}\"].ApiUrl // empty" "outputs-${ENV}.json")
  if [[ -n "$API_URL" ]]; then
    echo ""
    echo "API URL: http://${API_URL}"
    echo "Docs:    http://${API_URL}/docs"
  fi
fi
