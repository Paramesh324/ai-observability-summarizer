# WatsonX.ai Authentication Troubleshooting

## Error: "authentication_token_not_valid"

This error indicates the API key format or authentication method is incorrect.

## Root Causes

### 1. API Key Format Issues

**Problem**: The API key provided looks truncated or incomplete.

Your API key: `BHqOQh2to6_NeyExQt-_fRl1Ud0BMacEZP`

IBM Cloud API keys are typically **44 characters long** and follow this format:
- Start with uppercase letters
- Contains mix of letters, numbers, underscores, and hyphens
- Example: `AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_AbCd`

**Solution**: Verify you have the complete API key from IBM Cloud.

```bash
# Check API key length
echo -n "YOUR_API_KEY" | wc -c
# Should be around 44 characters

# Verify API key in secret
oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data.api-key}' | base64 -d | wc -c
```

### 2. Wrong Authentication Method

**Problem**: WatsonX.ai uses IBM Cloud IAM authentication, not simple API key auth.

IBM WatsonX.ai requires:
1. **IBM Cloud IAM API Key** (not WatsonX.ai project API key)
2. **Project ID** from your WatsonX.ai project
3. **Bearer token** generated from the IAM API key

**Current Implementation Issue**: The code is using OpenAI SDK which sends the API key as `Authorization: Bearer <api_key>`, but WatsonX.ai expects a proper IAM token.

### 3. Project ID Not in Request

**Problem**: Project ID must be in the request body or headers, not as URL query parameter.

**Current code** (incorrect):
```python
api_base_with_project = f"{api_base}?project_id={self.project_id}"
```

**Should be** (correct):
```python
# Project ID should be in request body or headers
headers = {"X-Project-Id": self.project_id}
# OR in request body
body = {"project_id": self.project_id, ...}
```

## Solutions

### Solution 1: Get Correct API Key

1. Go to [IBM Cloud API Keys](https://cloud.ibm.com/iam/apikeys)
2. Create a new API key or copy existing one
3. **Copy the FULL key** (it's only shown once!)
4. Update the secret:

```bash
# Delete old secret
oc delete secret ai-ibm-credentials -n ai-observability

# Create new secret with FULL API key
oc create secret generic ai-ibm-credentials \
  --from-literal=api-key='YOUR_FULL_44_CHAR_IBM_CLOUD_API_KEY' \
  --from-literal=project-id='YOUR_PROJECT_ID' \
  -n ai-observability

# Restart MCP server
oc rollout restart deployment aiobs-mcp-server -n ai-observability
```

### Solution 2: Fix Authentication Method (Code Change Required)

The IBM bot needs to be updated to use proper IBM Cloud IAM authentication:

```python
# Instead of using OpenAI SDK directly, we need to:
# 1. Exchange IAM API key for access token
# 2. Use access token in Authorization header
# 3. Include project_id in request body

import requests

def get_iam_token(api_key: str) -> str:
    """Get IBM Cloud IAM access token from API key."""
    url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey": api_key
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json()["access_token"]

# Then use the token
access_token = get_iam_token(api_key)
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}
```

### Solution 3: Verify Current Deployment

Check if the new code with project ID support is actually deployed:

```bash
# Check MCP server logs for project ID
oc logs deployment/aiobs-mcp-server -n ai-observability | grep -i "project"

# Expected output:
# "WatsonX.ai project ID configured: adcd4b4b..."

# If you don't see this, the new code is NOT deployed yet
```

### Solution 4: Use IBM WatsonX.ai Python SDK

Instead of OpenAI SDK, use the official IBM SDK:

```bash
# Install IBM WatsonX.ai SDK
pip install ibm-watsonx-ai
```

```python
from ibm_watsonx_ai import APIClient
from ibm_watsonx_ai.foundation_models import ModelInference

# Initialize client
client = APIClient({
    "url": "https://us-south.ml.cloud.ibm.com",
    "apikey": api_key
})

# Create model inference
model = ModelInference(
    model_id="ibm/granite-13b-chat-v2",
    credentials=client.credentials,
    project_id=project_id
)

# Generate
response = model.generate_text(prompt="Hello")
```

## Immediate Action Items

### 1. Verify API Key

```bash
# Check current API key length
oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data.api-key}' | base64 -d
# Copy the output and count characters

# If it's not ~44 characters, get a new one from IBM Cloud
```

### 2. Check if New Code is Deployed

```bash
# Check pod image
oc get deployment aiobs-mcp-server -n ai-observability -o jsonpath='{.spec.template.spec.containers[0].image}'

# Check pod logs for project ID support
oc logs deployment/aiobs-mcp-server -n ai-observability | tail -50
```

### 3. Test API Key Directly

```bash
# Test IBM Cloud IAM token generation
curl -X POST "https://iam.cloud.ibm.com/identity/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=YOUR_API_KEY"

# Should return JSON with "access_token"
```

### 4. Test WatsonX.ai API Directly

```bash
# Get IAM token first
IAM_TOKEN=$(curl -X POST "https://iam.cloud.ibm.com/identity/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=YOUR_API_KEY" \
  | jq -r '.access_token')

# Test WatsonX.ai API
curl -X POST "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29" \
  -H "Authorization: Bearer ${IAM_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "ibm/granite-13b-chat-v2",
    "project_id": "YOUR_PROJECT_ID",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

## Next Steps

Based on the error, you need to:

1. **Get the complete IBM Cloud IAM API key** (44 chars)
2. **Verify the new code with project ID support is deployed**
3. **Consider implementing proper IBM IAM authentication** (code change)

The current implementation using OpenAI SDK may not work correctly with WatsonX.ai's authentication requirements.

## Alternative: Use IBM WatsonX.ai SDK

The most reliable solution is to update the IBM bot to use the official IBM WatsonX.ai Python SDK instead of the OpenAI SDK. This would require code changes to `src/chatbots/ibm_bot.py`.

Would you like me to implement this fix?