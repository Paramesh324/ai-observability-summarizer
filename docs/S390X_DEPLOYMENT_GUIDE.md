# AI Observability Summarizer - s390x Deployment Guide

Complete end-to-end guide for deploying the AI Observability Summarizer on s390x OpenShift clusters with IBM WatsonX.ai integration.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Build & Deploy](#build--deploy)
3. [IBM WatsonX.ai Setup](#ibm-watsonxai-setup)
4. [Verification & Testing](#verification--testing)
5. [Troubleshooting](#troubleshooting)

## Prerequisites

**Required:**
- OpenShift 4.12+ on s390x
- Docker/Podman with s390x support
- `oc` CLI, Helm 3.x, Git
- IBM Cloud account with WatsonX.ai access

**Resources:**
- MCP Server: 500m CPU, 1Gi RAM
- Console Plugin: 100m CPU, 256Mi RAM

## Build & Deploy

### 1. Build Images for s390x

```bash
# MCP Server
docker buildx build --platform linux/s390x \
  -f src/mcp_server/Dockerfile \
  -t quay.io/<org>/aiobs-mcp-server:s390x \
  --push .

# Console Plugin
cd openshift-plugin
docker buildx build --platform linux/s390x \
  -f Dockerfile.plugin \
  -t quay.io/<org>/aiobs-console-plugin:s390x \
  --push .
```

### 2. Deploy to OpenShift

```bash
# Enable monitoring
./scripts/enable-user-workload-monitoring.sh

# Install operators
./scripts/operator-manager.sh install all

# Create namespace
oc create namespace ai-observability
oc project ai-observability

# Deploy with Helm
cd deploy/helm/mcp-server
helm install aiobs-mcp-server . \
  --set image.repository=quay.io/<org>/aiobs-mcp-server \
  --set image.tag=s390x \
  -n ai-observability

cd ../console-plugin
helm install aiobs-console-plugin . \
  --set image.repository=quay.io/<org>/aiobs-console-plugin \
  --set image.tag=s390x \
  -n ai-observability

# Enable plugin
oc patch consoles.operator.openshift.io cluster \
  --type=json \
  --patch='[{"op": "add", "path": "/spec/plugins/-", "value": "aiobs-console-plugin"}]'
```

## IBM WatsonX.ai Setup

### Get Credentials

1. **API Key**: https://cloud.ibm.com/iam/apikeys → Create API key
2. **Project ID**: https://dataplatform.cloud.ibm.com/wx/home → Project settings

### Create Secret

```bash
oc create secret generic ai-ibm-credentials \
  --from-literal=api-key='YOUR_IBM_CLOUD_API_KEY' \
  --from-literal=project-id='YOUR_WATSONX_PROJECT_ID' \
  -n ai-observability
```

### Configure Models

```bash
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ai-model-config
  namespace: ai-observability
data:
  model-config.json: |
    {
      "ibm/llama-3-1-70b-instruct": {
        "provider": "ibm",
        "apiUrl": "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat",
        "modelName": "meta-llama/llama-3-1-70b-instruct"
      },
      "ibm/granite-13b-chat-v2": {
        "provider": "ibm",
        "apiUrl": "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat",
        "modelName": "ibm/granite-13b-chat-v2"
      }
    }
EOF

oc rollout restart deployment aiobs-mcp-server -n ai-observability
```

## Verification & Testing

```bash
# Check pods
oc get pods -n ai-observability

# Check logs for IAM token
oc logs deployment/aiobs-mcp-server -n ai-observability | grep -i "IAM"
# Should see: "✅ IAM token obtained"

# Test API
oc port-forward svc/aiobs-mcp-server 8000:8000 -n ai-observability &
curl http://localhost:8000/health

# Test WatsonX.ai
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"model_name": "ibm/granite-13b-chat-v2", "message": "Hello"}'
```

## Troubleshooting

### 401 Authentication Error

**Cause**: Invalid API key or missing IAM token exchange

**Fix**:
```bash
# Test IAM token generation
curl -X POST "https://iam.cloud.ibm.com/identity/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=YOUR_API_KEY"

# Should return JSON with "access_token"
# If error, regenerate API key from IBM Cloud
```

### Image Not Updating

```bash
# Use unique tags
TAG="s390x-$(date +%Y%m%d-%H%M%S)"
docker buildx build --platform linux/s390x \
  -t quay.io/<org>/aiobs-mcp-server:${TAG} --push .

oc set image deployment/aiobs-mcp-server \
  mcp-server=quay.io/<org>/aiobs-mcp-server:${TAG} \
  -n ai-observability
```

### Pod Not Starting

```bash
# Check events
oc describe pod <pod-name> -n ai-observability

# Check image
oc get pods -n ai-observability -o jsonpath='{.items[*].spec.containers[*].image}'
```

## Key Points

- **Authentication**: WatsonX.ai uses IBM Cloud IAM tokens (not simple API keys)
- **Project ID**: Required in every API request
- **Token Refresh**: IAM tokens expire after 1 hour, auto-refreshed by the bot
- **s390x**: All images must be built with `--platform linux/s390x`

## Resources

- [IBM WatsonX.ai Docs](https://www.ibm.com/docs/en/watsonx-as-a-service)
- [OpenShift Docs](https://docs.openshift.com/)
- [Project README](../README.md)