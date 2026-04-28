# IBM WatsonX.ai Quick Start Guide

Quick reference for setting up IBM WatsonX.ai with the AI Observability Summarizer.

## What You Need

1. **IBM Cloud Account** with WatsonX.ai access
2. **WatsonX.ai Project** created
3. **API Key** from IBM Cloud IAM
4. **Project ID** from your WatsonX.ai project

## Getting Credentials

### 1. Get API Key

```bash
# Option A: From IBM Cloud Console
1. Go to https://cloud.ibm.com/iam/apikeys
2. Click "Create an IBM Cloud API key"
3. Give it a name (e.g., "watsonx-aiobs")
4. Copy the API key (you won't see it again!)

# Option B: Using IBM Cloud CLI
ibmcloud iam api-key-create watsonx-aiobs -d "WatsonX.ai for AI Observability"
```

### 2. Get Project ID

```bash
# From WatsonX.ai Console
1. Go to https://dataplatform.cloud.ibm.com/wx/home
2. Open your project
3. Go to "Manage" tab → "General"
4. Copy the "Project ID"
```

## Setup on OpenShift

### 1. Create Secret

```bash
# Replace with your actual credentials
oc create secret generic ai-ibm-credentials \
  --from-literal=api-key='YOUR_WATSONX_API_KEY_HERE' \
  --from-literal=project-id='YOUR_WATSONX_PROJECT_ID_HERE' \
  --namespace ai-observability
```

### 2. Verify Secret

```bash
# Check secret exists
oc get secret ai-ibm-credentials -n ai-observability

# Verify it has both keys
oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data}' | jq 'keys'
# Should show: ["api-key", "project-id"]
```

### 3. Restart MCP Server

```bash
# Restart to pick up the new credentials
oc rollout restart deployment aiobs-mcp-server -n ai-observability

# Wait for rollout to complete
oc rollout status deployment aiobs-mcp-server -n ai-observability
```

### 4. Verify in Logs

```bash
# Check that project ID is loaded
oc logs deployment/aiobs-mcp-server -n ai-observability | grep -i "project"

# You should see:
# "WatsonX.ai project ID configured: 12345678..."
```

## Available Models

The following IBM WatsonX.ai models are pre-configured:

| Model ID | Description | Best For |
|----------|-------------|----------|
| `ibm/llama-3-1-70b-instruct` | Meta Llama 3.1 70B | Complex analysis, detailed responses |
| `ibm/granite-13b-chat-v2` | IBM Granite 13B | Fast responses, efficient |

## Testing

### Quick Test via CLI

```bash
# Port-forward to MCP server
oc port-forward svc/aiobs-mcp-server 8000:8000 -n ai-observability &

# Test chat with IBM model
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "ibm/llama-3-1-70b-instruct",
    "message": "What is the current time?",
    "namespace": "ai-observability"
  }' | jq .
```

### Test via UI

1. Open OpenShift Console
2. Navigate to **AI Observability** plugin
3. Go to **Settings** → **AI Model Configuration**
4. Select **IBM WatsonX.ai** provider
5. Choose model: `ibm/llama-3-1-70b-instruct`
6. Click **Test Connection**
7. Go to **Chat** tab
8. Ask: "Show me pod CPU usage"

## Troubleshooting

### Error: "project_id required"

**Cause**: Project ID not set in secret or not loaded by bot

**Fix**:
```bash
# Verify project-id exists in secret
oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data.project-id}' | base64 -d

# If empty, recreate secret with project-id
oc delete secret ai-ibm-credentials -n ai-observability
oc create secret generic ai-ibm-credentials \
  --from-literal=api-key='YOUR_API_KEY' \
  --from-literal=project-id='YOUR_PROJECT_ID' \
  --namespace ai-observability

# Restart MCP server
oc rollout restart deployment aiobs-mcp-server -n ai-observability
```

### Error: "401 Unauthorized"

**Cause**: Invalid or expired API key

**Fix**:
```bash
# Generate new API key from IBM Cloud
# Then update secret
oc create secret generic ai-ibm-credentials \
  --from-literal=api-key='NEW_API_KEY' \
  --from-literal=project-id='YOUR_PROJECT_ID' \
  --namespace ai-observability \
  --dry-run=client -o yaml | oc apply -f -

# Restart MCP server
oc rollout restart deployment aiobs-mcp-server -n ai-observability
```

### Error: "Connection timeout"

**Cause**: Network connectivity issues or wrong endpoint

**Fix**:
```bash
# Verify endpoint in model config
oc get configmap ai-model-config -n ai-observability -o jsonpath='{.data.model-config\.json}' | jq '.["ibm/llama-3-1-70b-instruct"].apiUrl'

# Should be: "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat"

# Test connectivity from pod
oc exec -it deployment/aiobs-mcp-server -n ai-observability -- \
  curl -v https://us-south.ml.cloud.ibm.com/ml/v1/text/chat
```

## Code Changes Summary

The following code changes enable WatsonX.ai project ID support:

### 1. `src/core/api_key_manager.py`
- Added `fetch_project_id_from_secret()` function
- Fetches `project-id` from `ai-ibm-credentials` secret

### 2. `src/chatbots/ibm_bot.py`
- Added `project_id` parameter to `__init__()`
- Reads project ID from parameter or environment
- Appends project ID as query parameter to API URL
- Sets `WATSONX_PROJECT_ID` environment variable

### 3. `src/chatbots/factory.py`
- Fetches project ID from secret when creating IBM bot
- Passes project ID to `IBMBobChatBot` constructor

## Next Steps

After successful setup:

1. **Configure Model in UI**: Select IBM WatsonX.ai model in settings
2. **Test Queries**: Try various observability questions
3. **Monitor Usage**: Check IBM Cloud for API usage and costs
4. **Optimize**: Adjust model selection based on performance needs

## Resources

- [IBM WatsonX.ai Documentation](https://www.ibm.com/docs/en/watsonx-as-a-service)
- [IBM Cloud API Keys](https://cloud.ibm.com/docs/account?topic=account-userapikey)
- [Complete s390x Deployment Guide](S390X_DEPLOYMENT_GUIDE.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)