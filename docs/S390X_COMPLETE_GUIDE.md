# Complete s390x End-to-End Guide

Single comprehensive guide for building, deploying, and testing AI Observability Summarizer on s390x OpenShift clusters.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Build Images](#build-images)
4. [Deploy to OpenShift](#deploy-to-openshift)
5. [Test and Verify](#test-and-verify)
6. [Troubleshooting](#troubleshooting)

---

## Overview

**All Dockerfiles are already s390x-compatible!** They use Red Hat UBI9 base images with native s390x support. **No Dockerfile changes needed.**

### Components

| Component | Dockerfile | Base Image | Status |
|-----------|-----------|------------|--------|
| MCP Server | `src/mcp_server/Dockerfile` | UBI9 Python 3.11 | ✅ Ready |
| Alerting | `src/alerting/Dockerfile` | UBI9 Python 3.11 | ✅ Ready |
| Console Plugin | `openshift-plugin/Dockerfile.plugin` | UBI9 Nginx 1.20 | ✅ Ready |
| React UI | `openshift-plugin/Dockerfile.react-ui` | Node:24 + UBI9 Nginx | ✅ Ready |

---

## Prerequisites

### 1. Verify s390x Environment

```bash
# Check architecture
uname -m
# Expected: s390x

# Check available tools
oc version      # OpenShift CLI
helm version    # Helm 3.x
podman version  # Container tool
yq --version    # YAML processor
jq --version    # JSON processor
```

### 2. Login to OpenShift

```bash
# Login to s390x OpenShift cluster
oc login --server=https://api.your-s390x-cluster.example.com:6443

# Verify cluster architecture
oc get nodes -o jsonpath='{.items[*].status.nodeInfo.architecture}' | tr ' ' '\n' | sort -u
# Must show: s390x

# Check OpenShift version (should be 4.18.33+)
oc version
```

### 3. Login to Container Registry

```bash
# Login to quay.io (or your registry)
podman login quay.io
```

### 4. Set Environment Variables

```bash
export NAMESPACE=ai-observability
export REGISTRY=quay.io
export ORG=your-org
export VERSION=2.0.0
export PLATFORM=linux/s390x
export LLM_URL=https://api.openai.com/v1  # Or your LLM endpoint
```

### 5. Install OpenShift AI (Required)

**OpenShift AI is required** to host the LLM that powers the observability analysis.

#### Check if OpenShift AI is Already Installed

```bash
# Check for OpenShift AI operator
oc get csv -A | grep -i "rhods-operator\|opendatahub"

# Check OpenShift AI version
oc get dsci -A
```

#### Install OpenShift AI on s390x

If OpenShift AI is not installed, follow these steps:

**Option 1: Via OpenShift Console (Recommended)**

1. Navigate to **OperatorHub** in the OpenShift Console
2. Search for "**Red Hat OpenShift AI**" or "**OpenDataHub**"
3. Click **Install**
4. Select installation mode:
   - **All namespaces** (recommended)
   - Or specific namespace
5. Click **Install** and wait for completion (2-3 minutes)

**Option 2: Via CLI**

```bash
# Create subscription for OpenShift AI operator
cat <<EOF | oc apply -f -
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: rhods-operator
  namespace: openshift-operators
spec:
  channel: stable
  name: rhods-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
EOF

# Wait for operator to be ready
oc wait --for=condition=Ready pod -l name=rhods-operator -n openshift-operators --timeout=300s

# Create DataScienceCluster instance
cat <<EOF | oc apply -f -
apiVersion: datasciencecluster.opendatahub.io/v1
kind: DataScienceCluster
metadata:
  name: default-dsc
spec:
  components:
    dashboard:
      managementState: Managed
    workbenches:
      managementState: Managed
    modelmeshserving:
      managementState: Managed
    datasciencepipelines:
      managementState: Managed
    kserve:
      managementState: Managed
EOF
```

#### Verify OpenShift AI Installation

```bash
# Check operator status
oc get csv -n openshift-operators | grep rhods

# Check DataScienceCluster
oc get datasciencecluster -A

# Check OpenShift AI pods
oc get pods -n redhat-ods-applications
oc get pods -n redhat-ods-operator

# Verify version (should be 2.16.2+)
oc get datasciencecluster default-dsc -o jsonpath='{.status.release.version}'
```

**Expected output:**
- OpenShift AI operator: `Succeeded`
- DataScienceCluster: `Ready`
- All pods in `redhat-ods-*` namespaces: `Running`

#### Deploy LLM on OpenShift AI (Optional)

If you want to deploy your own LLM instead of using an external endpoint:

```bash
# This will be deployed as part of the main installation
# The LLM will run on available accelerators (GPU/CPU)
# Skip this if using external LLM_URL
```

**Note**: For s390x, ensure your LLM model supports the architecture. Most models work, but check model documentation.

---

## Build Images

### Option 1: Build All with Makefile (Recommended)

```bash
cd /path/to/ai-observability-summarizer

# Build all 4 components
make build PLATFORM=${PLATFORM} REGISTRY=${REGISTRY} ORG=${ORG} VERSION=${VERSION}

# Expected output:
# ✅ metrics-alerting image built
# ✅ mcp-server image built
# ✅ console-plugin image built
# ✅ react-ui image built

# Push all images
make push REGISTRY=${REGISTRY} ORG=${ORG} VERSION=${VERSION}
```

### Option 2: Build Individual Components

#### Build MCP Server

```bash
podman build --platform ${PLATFORM} \
  -f src/mcp_server/Dockerfile \
  -t ${REGISTRY}/${ORG}/aiobs-mcp-server:${VERSION} \
  src

# Verify architecture
podman inspect ${REGISTRY}/${ORG}/aiobs-mcp-server:${VERSION} --format '{{.Architecture}}'
# Expected: s390x

# Push
podman push ${REGISTRY}/${ORG}/aiobs-mcp-server:${VERSION}
```

#### Build Alerting Service

```bash
podman build --platform ${PLATFORM} \
  -f src/alerting/Dockerfile \
  -t ${REGISTRY}/${ORG}/aiobs-metrics-alerting:${VERSION} \
  src

podman push ${REGISTRY}/${ORG}/aiobs-metrics-alerting:${VERSION}
```

#### Build Console Plugin

```bash
# Build assets first
cd openshift-plugin
yarn install --frozen-lockfile
yarn build
cd ..

# Build container
podman build --platform ${PLATFORM} \
  -f openshift-plugin/Dockerfile.plugin \
  -t ${REGISTRY}/${ORG}/aiobs-console-plugin:${VERSION} \
  openshift-plugin

podman push ${REGISTRY}/${ORG}/aiobs-console-plugin:${VERSION}
```

#### Build React UI

```bash
# Build assets first
cd openshift-plugin
yarn install --frozen-lockfile
yarn build:react-ui
cd ..

# Build container
podman build --platform ${PLATFORM} \
  -f openshift-plugin/Dockerfile.react-ui \
  -t ${REGISTRY}/${ORG}/aiobs-react-ui:${VERSION} \
  openshift-plugin

podman push ${REGISTRY}/${ORG}/aiobs-react-ui:${VERSION}
```

### Verify All Images

```bash
# Check all images are s390x
for img in mcp-server metrics-alerting console-plugin react-ui; do
  echo "Checking aiobs-${img}..."
  podman inspect ${REGISTRY}/${ORG}/aiobs-${img}:${VERSION} --format '{{.Architecture}}'
done
# All should show: s390x
```

---

## Deploy to OpenShift

### Step 1: Install Operators

```bash
# Create namespace
oc create namespace ${NAMESPACE}
oc project ${NAMESPACE}

# Install all required operators
make install-operators NAMESPACE=${NAMESPACE}

# Wait for operators to be ready (2-3 minutes)
sleep 120

# Verify operators
make check-operators

# Check operator pods
oc get pods -n openshift-cluster-observability-operator
oc get pods -n openshift-opentelemetry-operator
oc get pods -n openshift-tempo-operator
oc get pods -n openshift-logging
```

**Expected operators:**
- Cluster Observability Operator
- OpenTelemetry Operator
- Tempo Operator
- OpenShift Logging Operator
- Loki Operator

### Step 2: Deploy Observability Stack

```bash
# Install MinIO (storage backend)
make install-minio NAMESPACE=${NAMESPACE} \
  MINIO_USER=admin \
  MINIO_PASSWORD=minio123 \
  MINIO_BUCKETS=tempo,loki

# Wait for MinIO
sleep 30

# Check MinIO
oc get pods -n observability-hub | grep minio

# Install complete observability stack
make install-observability-stack NAMESPACE=${NAMESPACE}

# Wait for stack (1-2 minutes)
sleep 60

# Check all components
oc get pods -n observability-hub
oc get pods -n openshift-logging
oc get pods -n openshift-cluster-observability-operator
```

**Expected components:**
- MinIO (object storage)
- TempoStack (distributed tracing)
- LokiStack (log aggregation)
- OpenTelemetry Collector
- Korrel8r (signal correlation)

### Step 3: Deploy AI Observability

#### Option A: Console Plugin Mode (Production)

```bash
make install NAMESPACE=${NAMESPACE} \
  REGISTRY=${REGISTRY} \
  ORG=${ORG} \
  VERSION=${VERSION} \
  LLM_URL=${LLM_URL} \
  DEV_MODE=false

# Wait for deployment
sleep 60

# Check pods
oc get pods -n ${NAMESPACE}
```

**Expected pods:**
- aiobs-mcp-server-* (Running)
- aiobs-console-plugin-* (Running)

#### Option B: React UI Mode (Development)

```bash
make install NAMESPACE=${NAMESPACE} \
  REGISTRY=${REGISTRY} \
  ORG=${ORG} \
  VERSION=${VERSION} \
  LLM_URL=${LLM_URL} \
  DEV_MODE=true

# Check pods
oc get pods -n ${NAMESPACE}
```

**Expected pods:**
- aiobs-mcp-server-* (Running)
- aiobs-react-ui-* (Running)

### Step 4: Enable UI Features

```bash
# Enable tracing UI in OpenShift Console
make enable-tracing-ui

# Enable logging UI in OpenShift Console
make enable-logging-ui
```

### Step 5: Verify Deployment

```bash
# Check all pods are running
oc get pods -n ${NAMESPACE}

# Check services
oc get svc -n ${NAMESPACE}

# Check routes
oc get routes -n ${NAMESPACE}

# Verify pods are on s390x nodes
oc get pods -n ${NAMESPACE} -o wide
```

---

## Test and Verify

### Test 1: MCP Server Health

```bash
# Port-forward to MCP server
oc port-forward -n ${NAMESPACE} svc/aiobs-mcp-server-svc 8085:8085 &
PF_PID=$!

# Wait for port-forward
sleep 5

# Test health endpoint
curl http://localhost:8085/health
# Expected: {"status":"healthy"}

# Test config endpoint
curl http://localhost:8085/config | jq .
# Expected: JSON configuration

# Stop port-forward
kill $PF_PID
```

**✅ Pass Criteria:**
- Health endpoint returns healthy status
- Config endpoint returns valid JSON
- No connection errors

### Test 2: Console Plugin (DEV_MODE=false)

```bash
# Check plugin registration
oc get consoleplugin aiobs-console-plugin

# Check if enabled in console
oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}' | grep aiobs

# If not enabled, enable it
oc patch console.operator.openshift.io cluster \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/plugins/-", "value": "aiobs-console-plugin"}]'

# Wait for console to reload
sleep 30
```

**Access Console UI:**
1. Open OpenShift Console in browser
2. Navigate to **AI Observability** in left menu
3. Verify pages load:
   - OpenShift Metrics
   - vLLM Metrics
   - Hardware Accelerator
   - Chat with Prometheus

**✅ Pass Criteria:**
- AI Observability menu appears
- All pages load without errors
- No JavaScript errors in browser console

### Test 3: React UI (DEV_MODE=true)

```bash
# Get React UI URL
REACT_UI_URL=$(oc get route aiobs-react-ui -n ${NAMESPACE} -o jsonpath='{.spec.host}')
echo "React UI: https://${REACT_UI_URL}"
```

**Access React UI:**
1. Open the URL in browser
2. Login with OpenShift credentials
3. Verify dashboard loads
4. Navigate between pages

**✅ Pass Criteria:**
- Login works
- Dashboard loads
- Can navigate between pages
- No errors

### Test 4: Configure AI Model

**In the UI:**
1. Navigate to **Settings**
2. Click **Add API Key** or **Add Custom Model**
3. Configure your LLM provider:
   - **OpenAI**: Enter API key
   - **Google Gemini**: Enter API key
   - **Anthropic**: Enter API key
   - **Custom**: Enter model URL and token
4. Select model from dropdown

**✅ Pass Criteria:**
- Settings page loads
- Can configure LLM
- Model appears in dropdown

### Test 5: Chat with Prometheus

**In the UI:**
1. Go to **Chat with Prometheus**
2. Try these queries:
   - "Show me CPU usage for all pods in namespace default"
   - "What is the memory usage trend over the last hour?"
   - "Are there any pods with high restart counts?"

**✅ Pass Criteria:**
- Chat interface loads
- Queries return results
- Results are meaningful
- No errors in responses

### Test 6: Metrics Analysis

**In the UI:**
1. Go to **OpenShift Metrics**
2. Select namespace: `${NAMESPACE}`
3. Select time range: Last 1 hour
4. Click **Analyze**
5. Verify metrics are displayed
6. Try generating a report (HTML/PDF/Markdown)

**✅ Pass Criteria:**
- Metrics page loads
- Can select namespace and time range
- Analysis completes successfully
- Metrics are displayed
- Report generation works

### Test 7: Architecture Verification

```bash
# Verify all pods are on s390x nodes
for pod in $(oc get pods -n ${NAMESPACE} -o name); do
  node=$(oc get $pod -n ${NAMESPACE} -o jsonpath='{.spec.nodeName}')
  arch=$(oc get node $node -o jsonpath='{.status.nodeInfo.architecture}')
  echo "$pod on $node ($arch)"
done
# All should show s390x
```

**✅ Pass Criteria:**
- All pods running on s390x nodes
- No pods on non-s390x nodes

### Test 8: Performance Check

```bash
# Check pod resource usage
oc adm top pods -n ${NAMESPACE}

# Check node resource usage
oc adm top nodes

# Load test MCP server
oc port-forward -n ${NAMESPACE} svc/aiobs-mcp-server-svc 8085:8085 &
PF_PID=$!

# Run 10 concurrent requests
for i in {1..10}; do
  (time curl -s http://localhost:8085/health > /dev/null) &
done
wait

kill $PF_PID
```

**✅ Pass Criteria:**
- Pods are within resource limits
- No OOMKilled pods
- All requests complete successfully
- Response times are reasonable (<1s)

### Test 9: Integration Testing

```bash
# Test Prometheus integration
oc port-forward -n ${NAMESPACE} svc/aiobs-mcp-server-svc 8085:8085 &
PF_PID=$!

curl -s "http://localhost:8085/api/metrics?query=up" | jq .

kill $PF_PID
```

**Test Tempo Integration (if enabled):**
1. Go to **Observe → Traces**
2. Select a service
3. View trace details

**Test Loki Integration (if enabled):**
1. Go to **Observe → Logs**
2. Select a namespace
3. View logs

**✅ Pass Criteria:**
- Prometheus queries return results
- Can query traces (if Tempo enabled)
- Can query logs (if Loki enabled)

### Test 10: Upgrade Test

```bash
# Test Helm upgrade
helm upgrade mcp-server deploy/helm/mcp-server \
  -n ${NAMESPACE} \
  --set resources.requests.cpu=2

# Wait for rollout
oc rollout status deployment/aiobs-mcp-server -n ${NAMESPACE}

# Verify upgrade
oc get deployment aiobs-mcp-server -n ${NAMESPACE} -o yaml | grep cpu
```

**✅ Pass Criteria:**
- Upgrade completes successfully
- New configuration is applied
- No downtime

---

## Troubleshooting

### Issue 1: Build Fails with "Exec format error"

**Cause:** Trying to run s390x containers on non-s390x machine

**Solution:** This is expected on Mac/x86_64. The build completed successfully, but you can't run the container locally. Deploy to s390x cluster instead.

### Issue 2: Pods in ImagePullBackOff

**Symptoms:**
```bash
oc get pods -n ${NAMESPACE}
# aiobs-mcp-server-xxx   0/1   ImagePullBackOff
```

**Solutions:**
```bash
# Check image exists and is s390x
podman inspect ${REGISTRY}/${ORG}/aiobs-mcp-server:${VERSION} --format '{{.Architecture}}'

# Check image pull secrets
oc get secrets -n ${NAMESPACE} | grep pull

# Check pod events
oc describe pod <pod-name> -n ${NAMESPACE}

# Verify registry login
podman login --get-login ${REGISTRY}
```

### Issue 3: Console Plugin Not Appearing

**Symptoms:** AI Observability menu not visible in OpenShift Console

**Solutions:**
```bash
# Check plugin registration
oc get consoleplugin aiobs-console-plugin

# Check if plugin is enabled
oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}'

# Manually enable plugin
oc patch console.operator.openshift.io cluster \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/plugins/-", "value": "aiobs-console-plugin"}]'

# Restart console pods
oc delete pods -n openshift-console -l app=console

# Wait and refresh browser
```

### Issue 4: MCP Server Not Starting

**Symptoms:**
```bash
oc logs deployment/aiobs-mcp-server -n ${NAMESPACE}
# Error: Connection refused to Prometheus
```

**Solutions:**
```bash
# Check Prometheus URL
oc get deployment aiobs-mcp-server -n ${NAMESPACE} -o yaml | grep PROMETHEUS_URL

# Test Prometheus connectivity
oc run test-curl --image=curlimages/curl --rm -it -- \
  curl -k https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query?query=up

# Update configuration if needed
helm upgrade mcp-server deploy/helm/mcp-server \
  -n ${NAMESPACE} \
  --set env.PROMETHEUS_URL=https://thanos-querier.openshift-monitoring.svc.cluster.local:9091
```

### Issue 5: Operators Not Installing

**Symptoms:** Operator installation fails

**Solutions:**
```bash
# Check operator status
oc get csv -A | grep -E 'observability|tempo|loki|logging|opentelemetry'

# Check operator logs
oc logs -n openshift-operators deployment/cluster-logging-operator

# Verify cluster has required permissions
oc auth can-i create clusterroles --as=system:serviceaccount:${NAMESPACE}:default

# Reinstall operators
make uninstall-operators
make install-operators NAMESPACE=${NAMESPACE}
```

### Issue 6: Observability Stack Issues

**Symptoms:** Tempo/Loki pods not starting

**Solutions:**
```bash
# Check MinIO is running
oc get pods -n observability-hub | grep minio

# Check operator logs
oc logs -n openshift-tempo-operator deployment/tempo-operator-controller
oc logs -n openshift-logging deployment/cluster-logging-operator

# Verify CRDs exist
oc get crd | grep -E 'tempo|loki'

# Check storage
oc get pvc -n observability-hub

# Reinstall if needed
make uninstall-observability-stack
make install-observability-stack NAMESPACE=${NAMESPACE}
```

### Issue 7: LLM Connection Fails

**Symptoms:** Chat queries fail with connection error

**Solutions:**
```bash
# Test LLM endpoint manually
curl -X POST ${LLM_URL}/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${LLM_API_TOKEN}" \
  -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"test"}]}'

# Check MCP server logs
oc logs deployment/aiobs-mcp-server -n ${NAMESPACE} | grep -i llm

# Update LLM configuration
helm upgrade mcp-server deploy/helm/mcp-server \
  -n ${NAMESPACE} \
  --set llm.url=${LLM_URL} \
  --set llm.apiToken=${LLM_API_TOKEN}
```

### Issue 8: Performance Issues

**Symptoms:** Slow response times, high resource usage

**Solutions:**
```bash
# Check resource usage
oc adm top pods -n ${NAMESPACE}
oc adm top nodes

# Increase resources
helm upgrade mcp-server deploy/helm/mcp-server \
  -n ${NAMESPACE} \
  --set resources.requests.cpu=2 \
  --set resources.requests.memory=2Gi \
  --set resources.limits.cpu=4 \
  --set resources.limits.memory=4Gi

# Check for resource constraints
oc describe pod <pod-name> -n ${NAMESPACE} | grep -A5 Events
```

### Getting Help

```bash
# Check all events
oc get events -n ${NAMESPACE} --sort-by='.lastTimestamp'

# Export logs for analysis
oc logs deployment/aiobs-mcp-server -n ${NAMESPACE} > mcp-server.log

# Check deployment status
make status NAMESPACE=${NAMESPACE}

# Review configuration
make config NAMESPACE=${NAMESPACE}
```

---

## Cleanup

### Uninstall AI Observability

```bash
make uninstall NAMESPACE=${NAMESPACE}

# Verify removal
oc get pods -n ${NAMESPACE}
# Should show no pods or namespace not found
```

### Uninstall Observability Stack (Optional)

```bash
make uninstall-observability-stack

# Verify removal
oc get pods -n observability-hub
oc get pods -n openshift-logging
```

### Uninstall Operators (Optional)

```bash
make uninstall-operators

# Verify removal
oc get csv -A | grep -E 'observability|tempo|loki|logging|opentelemetry'
```

---

## Quick Reference

### Build Commands

```bash
# Build all
make build PLATFORM=linux/s390x REGISTRY=quay.io ORG=your-org VERSION=2.0.0

# Push all
make push REGISTRY=quay.io ORG=your-org VERSION=2.0.0
```

### Deploy Commands

```bash
# Install operators
make install-operators NAMESPACE=ai-observability

# Install observability stack
make install-observability-stack NAMESPACE=ai-observability

# Install AI Observability (Console Plugin)
make install NAMESPACE=ai-observability \
  REGISTRY=quay.io ORG=your-org VERSION=2.0.0 \
  LLM_URL=https://api.openai.com/v1 \
  DEV_MODE=false

# Install AI Observability (React UI)
make install NAMESPACE=ai-observability \
  REGISTRY=quay.io ORG=your-org VERSION=2.0.0 \
  LLM_URL=https://api.openai.com/v1 \
  DEV_MODE=true
```

### Test Commands

```bash
# Check pods
oc get pods -n ai-observability

# Test MCP server
oc port-forward -n ai-observability svc/aiobs-mcp-server-svc 8085:8085 &
curl http://localhost:8085/health

# Check architecture
oc get pods -n ai-observability -o wide
```

### Automated Deployment

```bash
# Use the automated script
./scripts/deploy-s390x.sh --skip-build --skip-push
```

---

## Summary

This guide provides complete end-to-end instructions for:

1. ✅ **Building** - All 4 components for s390x (no Dockerfile changes needed)
2. ✅ **Deploying** - Complete stack with operators and observability
3. ✅ **Testing** - 10 comprehensive test scenarios
4. ✅ **Troubleshooting** - 8 common issues with solutions

### Key Points

- **Dockerfiles are s390x-ready** - Use Red Hat UBI9 base images
- **Makefile works with podman** - Fixed for s390x builds
- **Complete observability stack** - Tempo, Loki, OTEL, Korrel8r
- **Two UI modes** - Console Plugin (production) or React UI (development)
- **External LLM recommended** - OpenAI, Gemini, Anthropic, etc.

### Success Criteria

- ✅ All images build successfully for s390x
- ✅ All pods run on s390x nodes
- ✅ UI is accessible and functional
- ✅ Chat with Prometheus works
- ✅ Metrics analysis works
- ✅ Reports can be generated

You now have everything needed to deploy and test on s390x!