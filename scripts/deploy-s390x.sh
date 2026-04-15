#!/bin/bash
# Complete deployment script for s390x OpenShift clusters
# This script automates the entire deployment process for AI Observability Summarizer on s390x

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}ℹ ${1}${NC}"
}

print_success() {
    echo -e "${GREEN}✓ ${1}${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ ${1}${NC}"
}

print_error() {
    echo -e "${RED}✗ ${1}${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}${1}${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to wait for pods to be ready
wait_for_pods() {
    local namespace=$1
    local label=$2
    local timeout=${3:-300}
    
    print_info "Waiting for pods with label ${label} in namespace ${namespace}..."
    
    local elapsed=0
    while [ $elapsed -lt $timeout ]; do
        local ready=$(oc get pods -n ${namespace} -l ${label} -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null | grep -o "True" | wc -l)
        local total=$(oc get pods -n ${namespace} -l ${label} --no-headers 2>/dev/null | wc -l)
        
        if [ "$ready" -eq "$total" ] && [ "$total" -gt 0 ]; then
            print_success "All pods ready (${ready}/${total})"
            return 0
        fi
        
        echo -n "."
        sleep 5
        elapsed=$((elapsed + 5))
    done
    
    print_error "Timeout waiting for pods to be ready"
    return 1
}

# Function to verify architecture
verify_architecture() {
    print_header "Verifying s390x Architecture"
    
    local arch=$(oc get nodes -o jsonpath='{.items[0].status.nodeInfo.architecture}')
    
    if [ "$arch" != "s390x" ]; then
        print_error "Cluster architecture is ${arch}, not s390x"
        print_error "This script is designed for s390x clusters only"
        exit 1
    fi
    
    print_success "Cluster architecture verified: s390x"
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    local missing_tools=()
    
    for tool in oc helm yq jq podman; do
        if ! command_exists $tool; then
            missing_tools+=($tool)
        else
            print_success "$tool is installed"
        fi
    done
    
    if [ ${#missing_tools[@]} -gt 0 ]; then
        print_error "Missing required tools: ${missing_tools[*]}"
        print_info "Please install missing tools and try again"
        exit 1
    fi
    
    # Check if logged into OpenShift
    if ! oc whoami &>/dev/null; then
        print_error "Not logged into OpenShift cluster"
        print_info "Please run: oc login <cluster-url>"
        exit 1
    fi
    
    print_success "Logged in as: $(oc whoami)"
    print_success "Cluster: $(oc whoami --show-server)"
}

# Function to set configuration
set_configuration() {
    print_header "Configuration"
    
    # Required configuration
    export NAMESPACE=${NAMESPACE:-ai-observability}
    export REGISTRY=${REGISTRY:-quay.io}
    export ORG=${ORG:-ecosystem-appeng}
    export VERSION=${VERSION:-2.0.0}
    export PLATFORM=linux/s390x
    
    # Optional configuration
    export DEV_MODE=${DEV_MODE:-false}
    export MINIO_USER=${MINIO_USER:-admin}
    export MINIO_PASSWORD=${MINIO_PASSWORD:-minio123}
    export MINIO_BUCKETS=${MINIO_BUCKETS:-tempo,loki}
    
    # LLM Configuration
    if [ -z "$LLM_URL" ]; then
        print_warning "LLM_URL not set. You can:"
        print_info "  1. Use external API (recommended for s390x)"
        print_info "  2. Deploy local model (verify s390x compatibility)"
        print_info "  3. Configure later in UI"
        read -p "Enter LLM_URL (or press Enter to skip): " LLM_URL
        export LLM_URL
    fi
    
    print_info "Configuration:"
    print_info "  Namespace: ${NAMESPACE}"
    print_info "  Registry: ${REGISTRY}"
    print_info "  Organization: ${ORG}"
    print_info "  Version: ${VERSION}"
    print_info "  Platform: ${PLATFORM}"
    print_info "  Dev Mode: ${DEV_MODE}"
    print_info "  LLM URL: ${LLM_URL:-<not set>}"
}

# Function to build images
build_images() {
    print_header "Building Container Images for s390x"
    
    if [ "$SKIP_BUILD" = "true" ]; then
        print_warning "Skipping image build (SKIP_BUILD=true)"
        return 0
    fi
    
    print_info "Building all images with PLATFORM=${PLATFORM}..."
    
    if ! make build PLATFORM=${PLATFORM} REGISTRY=${REGISTRY} ORG=${ORG} VERSION=${VERSION}; then
        print_error "Image build failed"
        exit 1
    fi
    
    print_success "All images built successfully"
}

# Function to push images
push_images() {
    print_header "Pushing Images to Registry"
    
    if [ "$SKIP_PUSH" = "true" ]; then
        print_warning "Skipping image push (SKIP_PUSH=true)"
        return 0
    fi
    
    print_info "Pushing images to ${REGISTRY}/${ORG}..."
    
    if ! make push REGISTRY=${REGISTRY} ORG=${ORG} VERSION=${VERSION}; then
        print_error "Image push failed"
        exit 1
    fi
    
    print_success "All images pushed successfully"
}

# Function to install operators
install_operators() {
    print_header "Installing Required Operators"
    
    print_info "Installing operators..."
    
    if ! make install-operators NAMESPACE=${NAMESPACE}; then
        print_error "Operator installation failed"
        exit 1
    fi
    
    print_info "Waiting for operators to be ready..."
    sleep 30
    
    if ! make check-operators; then
        print_warning "Some operators may not be ready yet"
        print_info "Continuing anyway..."
    fi
    
    print_success "Operators installed"
}

# Function to install observability stack
install_observability() {
    print_header "Installing Observability Stack"
    
    print_info "Installing MinIO..."
    if ! make install-minio NAMESPACE=${NAMESPACE} \
        MINIO_USER=${MINIO_USER} \
        MINIO_PASSWORD=${MINIO_PASSWORD} \
        MINIO_BUCKETS=${MINIO_BUCKETS}; then
        print_error "MinIO installation failed"
        exit 1
    fi
    
    print_info "Installing observability components..."
    if ! make install-observability-stack NAMESPACE=${NAMESPACE}; then
        print_error "Observability stack installation failed"
        exit 1
    fi
    
    print_success "Observability stack installed"
}

# Function to deploy AI observability
deploy_ai_observability() {
    print_header "Deploying AI Observability Components"
    
    local install_args="NAMESPACE=${NAMESPACE} REGISTRY=${REGISTRY} ORG=${ORG} VERSION=${VERSION} DEV_MODE=${DEV_MODE}"
    
    if [ -n "$LLM_URL" ]; then
        install_args="${install_args} LLM_URL=${LLM_URL}"
    fi
    
    print_info "Deploying with: ${install_args}"
    
    if ! make install ${install_args}; then
        print_error "AI Observability deployment failed"
        exit 1
    fi
    
    print_success "AI Observability deployed"
}

# Function to enable UI features
enable_ui_features() {
    print_header "Enabling UI Features"
    
    print_info "Enabling tracing UI..."
    if make enable-tracing-ui; then
        print_success "Tracing UI enabled"
    else
        print_warning "Failed to enable tracing UI (may already be enabled)"
    fi
    
    print_info "Enabling logging UI..."
    if make enable-logging-ui; then
        print_success "Logging UI enabled"
    else
        print_warning "Failed to enable logging UI (may already be enabled)"
    fi
}

# Function to verify deployment
verify_deployment() {
    print_header "Verifying Deployment"
    
    print_info "Checking pods in ${NAMESPACE}..."
    oc get pods -n ${NAMESPACE}
    
    print_info "Checking services..."
    oc get svc -n ${NAMESPACE}
    
    print_info "Checking routes..."
    oc get routes -n ${NAMESPACE}
    
    print_info "Checking observability-hub namespace..."
    oc get pods -n observability-hub
    
    # Wait for main deployment to be ready
    if wait_for_pods ${NAMESPACE} "app=aiobs-mcp-server" 120; then
        print_success "MCP Server is ready"
    else
        print_warning "MCP Server may not be ready yet"
    fi
    
    if [ "$DEV_MODE" = "false" ]; then
        if wait_for_pods ${NAMESPACE} "app=aiobs-console-plugin" 120; then
            print_success "Console Plugin is ready"
        else
            print_warning "Console Plugin may not be ready yet"
        fi
    else
        if wait_for_pods ${NAMESPACE} "app=aiobs-react-ui" 120; then
            print_success "React UI is ready"
        else
            print_warning "React UI may not be ready yet"
        fi
    fi
}

# Function to display access information
display_access_info() {
    print_header "Access Information"
    
    if [ "$DEV_MODE" = "false" ]; then
        print_success "Console Plugin Mode"
        print_info "Access the AI Observability UI:"
        print_info "  1. Open OpenShift Console"
        print_info "  2. Navigate to 'AI Observability' in the left menu"
    else
        print_success "React UI Mode"
        local react_route=$(oc get route aiobs-react-ui -n ${NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-found")
        if [ "$react_route" != "not-found" ]; then
            print_info "React UI URL: https://${react_route}"
        else
            print_warning "React UI route not found"
        fi
    fi
    
    print_info ""
    print_info "MCP Server endpoint:"
    local mcp_route=$(oc get route aiobs-mcp-server-route -n ${NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "not-found")
    if [ "$mcp_route" != "not-found" ]; then
        print_info "  https://${mcp_route}"
    else
        print_info "  (internal only - no external route)"
    fi
    
    print_info ""
    print_info "Additional UI features:"
    print_info "  - Observe → Traces (if enabled)"
    print_info "  - Observe → Logs (if enabled)"
}

# Function to display next steps
display_next_steps() {
    print_header "Next Steps"
    
    print_info "1. Configure AI Model:"
    print_info "   - Navigate to Settings in the UI"
    print_info "   - Add API key or configure custom model"
    print_info "   - Supported: OpenAI, Gemini, Anthropic, Meta"
    
    print_info ""
    print_info "2. Explore Features:"
    print_info "   - OpenShift Metrics: Cluster and namespace analysis"
    print_info "   - vLLM Metrics: Model serving performance"
    print_info "   - Hardware Accelerator: GPU metrics (if available)"
    print_info "   - Chat with Prometheus: Natural language queries"
    
    print_info ""
    print_info "3. Generate Reports:"
    print_info "   - Export findings as HTML/PDF/Markdown"
    
    print_info ""
    print_info "4. Optional: Enable Alerting"
    print_info "   make install-with-alerts NAMESPACE=${NAMESPACE} SLACK_WEBHOOK_URL=<url>"
    
    print_info ""
    print_info "For troubleshooting, see: docs/S390X_DEPLOYMENT_GUIDE.md"
}

# Main deployment flow
main() {
    print_header "AI Observability Summarizer - s390x Deployment"
    
    # Step 1: Verify architecture
    verify_architecture
    
    # Step 2: Check prerequisites
    check_prerequisites
    
    # Step 3: Set configuration
    set_configuration
    
    # Confirm before proceeding
    echo ""
    read -p "Proceed with deployment? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        print_info "Deployment cancelled"
        exit 0
    fi
    
    # Step 4: Build images (optional)
    if [ "$SKIP_BUILD" != "true" ]; then
        build_images
    fi
    
    # Step 5: Push images (optional)
    if [ "$SKIP_PUSH" != "true" ]; then
        push_images
    fi
    
    # Step 6: Install operators
    install_operators
    
    # Step 7: Install observability stack
    install_observability
    
    # Step 8: Deploy AI observability
    deploy_ai_observability
    
    # Step 9: Enable UI features
    enable_ui_features
    
    # Step 10: Verify deployment
    verify_deployment
    
    # Display access information
    display_access_info
    
    # Display next steps
    display_next_steps
    
    print_header "Deployment Complete!"
    print_success "AI Observability Summarizer is now running on s390x"
}

# Handle script arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --skip-push)
            SKIP_PUSH=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-build    Skip building container images"
            echo "  --skip-push     Skip pushing images to registry"
            echo "  --help          Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  NAMESPACE       Target namespace (default: ai-observability)"
            echo "  REGISTRY        Container registry (default: quay.io)"
            echo "  ORG             Organization name (default: ecosystem-appeng)"
            echo "  VERSION         Image version (default: 2.0.0)"
            echo "  DEV_MODE        Deploy React UI instead of Console Plugin (default: false)"
            echo "  LLM_URL         External LLM endpoint URL"
            echo "  MINIO_USER      MinIO username (default: admin)"
            echo "  MINIO_PASSWORD  MinIO password (default: minio123)"
            echo ""
            echo "Example:"
            echo "  NAMESPACE=my-ns LLM_URL=https://api.openai.com/v1 $0"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run main deployment
main

# Made with Bob
