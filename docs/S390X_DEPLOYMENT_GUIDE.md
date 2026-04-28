# AI Observability Summarizer - s390x Deployment Guide

Complete end-to-end guide for deploying the AI Observability Summarizer on s390x OpenShift clusters with IBM WatsonX.ai integration.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Build Process](#build-process)
4. [Deployment Steps](#deployment-steps)
5. [IBM WatsonX.ai Configuration](#ibm-watsonxai-configuration)
6. [Verification](#verification)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools
- OpenShift CLI (`oc`)
- Docker or Podman with s390x support
- Helm 3.x
- Git

### OpenShift Cluster Requirements
- OpenShift 4.12+ on s390x architecture
- Cluster admin access for operator installation
- User workload monitoring enabled
- Sufficient resources (see resource requirements below)

### Resource Requirements
- **MCP Server**: 500m CPU, 1Gi memory
- **Console Plugin**: 100m CPU, 256Mi memory
- **Observability Stack**: Varies based on cluster size

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenShift Console                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         AI Observability Console Plugin              │   │
│  │  (React UI - s390x compatible)                       │   │
│  └────────────────────┬─────────────────────────────────┘   │
└───────────────────────┼─────────────────────────────────────┘
                        │ HTTP/HTTPS
                        ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Server (s390x container)                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastMCP Server                                      │   │
│  │  - Observability Tools                               │   │
│  │  - IBM WatsonX.ai Integration                        │   │
│  │  - Prometheus/Thanos Client                          │   │
│  │  - Tempo/Korrel8r Client                             │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────┬─────────────────────────────────────────────────┘
            │
            ├──────────► Thanos Querier (Metrics)
            ├──────────► Tempo (Traces)
            ├──────────► Korrel8r (Correlation)
            └──────────► IBM WatsonX.ai (AI Analysis)
```

## Build Process

### 1. Build MCP Server for s390x

```bash
# Navigate to project root
cd /path/to/ai-observability-summarizer

# Build MCP server image for s390x
docker buildx build \
  --platform linux/s390x \
  --file src/mcp_server/Dockerfile \
  --tag quay.io/<your-org>/aiobs-mcp-server:latest-s390x \
  --push \
  .

# Alternative: Build without cache (if needed)
docker buildx build \
  --platform linux/s390x \
  --no-cache \
  --file src/mcp_server/Dockerfile \
  --tag quay.io/<your-org>/aiobs-mcp-server:latest-s390x \
  --push \
  .
```

### 2. Build Console Plugin for s390x

```bash
# Navigate to plugin directory
cd openshift-plugin

# Build plugin image for s390x
docker buildx build \
  --platform linux/s390x \
  --file Dockerfile.plugin \
  --tag quay.io/<your-org>/aiobs-console-plugin:latest-s390x \
  --push \
  .
```

### 3. Build React UI for s390x (if needed)

```bash
# Still in openshift-plugin directory
docker buildx build \
  --platform linux/s390x \
  --file Dockerfile.react-ui \
  --tag quay.io/<your-org>/aiobs-react-ui:latest-s390x \
  --push \
  .
```

## Deployment Steps

### Step 1: Enable User Workload Monitoring

```bash
# Run the setup script
./scripts/enable-user-workload-monitoring.sh
```

Or manually:

```bash
# Create cluster-monitoring-config ConfigMap
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
EOF

# Create user-workload-monitoring-config ConfigMap
oc apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: user-workload-monitoring-config
  namespace: openshift-user-workload-monitoring
data:
  config.yaml: |
    prometheus:
      retention: 15d
      resources:
        requests:
          cpu: 200m
          memory: 2Gi
EOF
```

### Step 2: Install Required Operators

```bash
# Install operators using the operator manager script
./scripts/operator-manager.sh install all

# Or install individually:
./scripts/operator-manager.sh install loki
./scripts/operator-manager.sh install tempo
./scripts/operator-manager.sh install opentelemetry
./scripts/operator-manager.sh install logging
./scripts/operator-manager.sh install cluster-observability
```

### Step 3: Create Namespace

```bash
# Create namespace for the application
oc create namespace ai-observability

# Set as current namespace
oc project ai-observability
```

### Step 4: Deploy MCP Server

```bash
# Navigate to Helm chart directory
cd deploy/helm/mcp-server

# Update values.yaml with your s390x image
cat > values-s390x.yaml <<EOF
image:
  repository: quay.io/<your-org>/aiobs-mcp-server
  tag: latest-s390x
  pullPolicy: Always

replicaCount: 1

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: 1000m
    memory: 2Gi

# Disable OpenTelemetry auto-instrumentation for s390x
opentelemetry:
  autoInstrumentation: false

env:
  PROMETHEUS_URL: "https://thanos-querier.openshift-monitoring.svc.cluster.local:9091"
  TEMPO_URL: "https://tempo-gateway.openshift-tempo-operator.svc.cluster.local:8080"
  KORREL8R_URL: "http://korrel8r.openshift-observability-operator.svc.cluster.local:8080"
  PYTHON_LOG_LEVEL: "INFO"
  DEV_MODE: "false"
EOF

# Install with Helm
helm install aiobs-mcp-server . \
  --namespace ai-observability \
  --values values-s390x.yaml
```

### Step 5: Deploy Console Plugin

```bash
# Navigate to plugin Helm chart
cd ../console-plugin

# Update values.yaml with your s390x image
cat > values-s390x.yaml <<EOF
image:
  repository: quay.io/<your-org>/aiobs-console-plugin
  tag: latest-s390x
  pullPolicy: Always

replicaCount: 1

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 200m
    memory: 512Mi

service:
  type: ClusterIP
  port: 9443

plugin:
  name: aiobs-console-plugin
  displayName: "AI Observability"
  description: "AI-powered observability analysis"
EOF

# Install with Helm
helm install aiobs-console-plugin . \
  --namespace ai-observability \
  --values values-s390x.yaml
```

### Step 6: Enable Console Plugin

```bash
# Patch the console operator to enable the plugin
oc patch consoles.operator.openshift.io cluster \
  --type=json \
  --patch='[{"op": "add", "path": "/spec/plugins/-", "value": "aiobs-console-plugin"}]'

# Verify plugin is enabled
oc get consoles.operator.openshift.io cluster -o jsonpath='{.spec.plugins}'
```

## IBM WatsonX.ai Configuration

### Step 1: Obtain WatsonX.ai Credentials

1. Log in to [IBM Cloud](https://cloud.ibm.com)
2. Navigate to **Watson Studio** or **WatsonX.ai**
3. Create or select a project
4. Note down:
   - **API Key**: From IBM Cloud IAM
   - **Project ID**: From project settings
   - **API Endpoint**: Default is `https://us-south.ml.cloud.ibm.com/ml/v1/text/chat`

### Step 2: Create Kubernetes Secret

```bash
# Create secret with API key and project ID
oc create secret generic ai-ibm-credentials \
  --from-literal=api-key='<YOUR_WATSONX_API_KEY>' \
  --from-literal=project-id='<YOUR_WATSONX_PROJECT_ID>' \
  --namespace ai-observability

# Verify secret was created
oc get secret ai-ibm-credentials -n ai-observability
```

### Step 3: Update Model Configuration

The model configuration is stored in a ConfigMap. Update it with WatsonX.ai models:

```bash
# Get current ConfigMap
oc get configmap ai-model-config -n ai-observability -o yaml > model-config.yaml

# Edit to add IBM models (or use the provided model-config.json)
cat > model-config-update.yaml <<EOF
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
        "modelName": "meta-llama/llama-3-1-70b-instruct",
        "description": "IBM WatsonX.ai - Llama 3.1 70B Instruct"
      },
      "ibm/granite-13b-chat-v2": {
        "provider": "ibm",
        "apiUrl": "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat",
        "modelName": "ibm/granite-13b-chat-v2",
        "description": "IBM WatsonX.ai - Granite 13B Chat v2"
      }
    }
EOF

# Apply the updated ConfigMap
oc apply -f model-config-update.yaml

# Restart MCP server to pick up changes
oc rollout restart deployment aiobs-mcp-server -n ai-observability
```

### Step 4: Configure Model in UI

1. Open OpenShift Console
2. Navigate to **AI Observability** plugin
3. Go to **Settings** → **AI Model Configuration**
4. Select **IBM WatsonX.ai** as provider
5. Choose a model (e.g., `ibm/llama-3-1-70b-instruct`)
6. API key and project ID will be automatically loaded from the secret
7. Click **Save**

## Verification

### 1. Verify Deployments

```bash
# Check all pods are running
oc get pods -n ai-observability

# Expected output:
# NAME                                    READY   STATUS    RESTARTS   AGE
# aiobs-mcp-server-xxxxx                  1/1     Running   0          5m
# aiobs-console-plugin-xxxxx              1/1     Running   0          5m

# Check pod logs
oc logs -f deployment/aiobs-mcp-server -n ai-observability
oc logs -f deployment/aiobs-console-plugin -n ai-observability
```

### 2. Verify MCP Server Health

```bash
# Port-forward to MCP server
oc port-forward svc/aiobs-mcp-server 8000:8000 -n ai-observability

# In another terminal, check health endpoint
curl http://localhost:8000/health

# Expected output:
# {"status":"healthy","timestamp":"2024-01-15T10:30:00Z"}
```

### 3. Verify Console Plugin

```bash
# Check console operator status
oc get consoles.operator.openshift.io cluster -o yaml

# Verify plugin is listed in spec.plugins
# Look for: aiobs-console-plugin
```

### 4. Test IBM WatsonX.ai Integration

```bash
# Port-forward to MCP server
oc port-forward svc/aiobs-mcp-server 8000:8000 -n ai-observability

# Test chat endpoint with IBM model
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "ibm/llama-3-1-70b-instruct",
    "message": "What is the current CPU usage?",
    "namespace": "ai-observability"
  }'
```

### 5. End-to-End UI Test

1. Open OpenShift Console
2. Navigate to **AI Observability** plugin
3. Go to **Chat** tab
4. Select IBM WatsonX.ai model
5. Ask a question: "Show me pod CPU usage in namespace ai-observability"
6. Verify:
   - Progress indicators appear
   - Tool calls are executed (search_metrics, execute_promql)
   - Response is generated with metrics data
   - No errors in browser console

## Troubleshooting

### Issue: Pods Not Starting

**Symptoms**: Pods stuck in `Pending` or `ImagePullBackOff`

**Solutions**:
```bash
# Check pod events
oc describe pod <pod-name> -n ai-observability

# Verify image exists and is accessible
oc get pods -n ai-observability -o jsonpath='{.items[*].spec.containers[*].image}'

# Check image pull secrets if using private registry
oc get secrets -n ai-observability
```

### Issue: Network/DNS Problems During Build

**Symptoms**: Cannot resolve `pypi.org` during Docker build

**Solutions**:
```bash
# Option 1: Use a different DNS server
docker buildx build --build-arg DNS_SERVER=8.8.8.8 ...

# Option 2: Use a proxy
docker buildx build --build-arg HTTP_PROXY=http://proxy:port ...

# Option 3: Build on a different machine with network access
# Then push to registry and pull on s390x cluster
```

### Issue: IBM WatsonX.ai API Errors

**Symptoms**: 401 Unauthorized or 403 Forbidden errors

**Solutions**:
```bash
# Verify secret exists and has correct keys
oc get secret ai-ibm-credentials -n ai-observability -o yaml

# Check if API key is valid
API_KEY=$(oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data.api-key}' | base64 -d)
echo "API Key: ${API_KEY:0:10}..."

# Check if project ID is set
PROJECT_ID=$(oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data.project-id}' | base64 -d)
echo "Project ID: ${PROJECT_ID}"

# Verify MCP server can read the secret
oc exec -it deployment/aiobs-mcp-server -n ai-observability -- env | grep WATSONX
```

### Issue: Project ID Not Being Used

**Symptoms**: API calls fail with "project_id required" error

**Solutions**:
```bash
# Verify project ID is in the secret
oc get secret ai-ibm-credentials -n ai-observability -o jsonpath='{.data.project-id}' | base64 -d

# Check MCP server logs for project ID loading
oc logs deployment/aiobs-mcp-server -n ai-observability | grep -i "project"

# Restart MCP server to reload configuration
oc rollout restart deployment/aiobs-mcp-server -n ai-observability
```

### Issue: Console Plugin Not Appearing

**Symptoms**: Plugin not visible in OpenShift Console

**Solutions**:
```bash
# Verify plugin is enabled
oc get consoles.operator.openshift.io cluster -o jsonpath='{.spec.plugins}'

# Check console operator logs
oc logs -n openshift-console deployment/console-operator

# Verify plugin service is accessible
oc get svc aiobs-console-plugin -n ai-observability

# Force console refresh
# Clear browser cache and reload console
```

### Issue: Metrics Not Available

**Symptoms**: "No metrics found" or empty results

**Solutions**:
```bash
# Verify user workload monitoring is enabled
oc get configmap cluster-monitoring-config -n openshift-monitoring -o yaml

# Check Thanos Querier is accessible
oc get route -n openshift-monitoring | grep thanos

# Test Prometheus query directly
oc port-forward -n openshift-monitoring svc/thanos-querier 9091:9091
curl "http://localhost:9091/api/v1/query?query=up"

# Verify ServiceMonitor exists for your application
oc get servicemonitor -n ai-observability
```

## Additional Resources

- [OpenShift Documentation](https://docs.openshift.com/)
- [IBM WatsonX.ai Documentation](https://www.ibm.com/docs/en/watsonx-as-a-service)
- [Project README](../README.md)
- [Development Guide](DEV_GUIDE.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)

## Support

For issues or questions:
1. Check the [Troubleshooting Guide](TROUBLESHOOTING.md)
2. Review [GitHub Issues](https://github.com/your-org/ai-observability-summarizer/issues)
3. Contact the development team

## Version History

- **v1.0.0** (2024-01-15): Initial s390x deployment guide
  - Complete build and deployment instructions
  - IBM WatsonX.ai integration
  - Troubleshooting section