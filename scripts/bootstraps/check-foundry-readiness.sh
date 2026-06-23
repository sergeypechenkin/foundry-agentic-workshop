#!/bin/bash
# =============================================================================
# check-foundry-readiness.sh
# Validates Foundry capability hosts status and agent IAM role assignments.
#
# Reads defaults from .env file (repo root), CLI arguments override .env values.
# =============================================================================

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Defaults ---
API_VERSION="2025-04-01-preview"

# --- Resolve repo root and load .env ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"

if [[ -f "$ENV_FILE" ]]; then
    # Source .env, stripping surrounding quotes from values
    set -a
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^# ]] && continue
        # Remove surrounding quotes from value
        value="${value%\"}"
        value="${value#\"}"
        export "$key=$value"
    done < "$ENV_FILE"
    set +a
fi

# --- Usage ---
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Checks Foundry capability hosts and agent IAM role assignments.
Loads defaults from .env file at repo root (override with ENV_FILE env var).

Required (or set via .env):
  --resource-group, -g    Resource group name          (.env: AZURE_RESOURCE_GROUP)
  --account-name, -a      AI Services (Foundry) account (.env: AI_FOUNDRY_HUB_NAME)
  --project-name, -p      AI Foundry project name      (.env: AI_FOUNDRY_PROJECT_NAME)

Optional:
  --subscription-id, -s   Subscription ID (defaults to current az subscription)
  --storage-account       Storage account name         (.env: AZURE_STORAGE_ACCOUNT_NAME)
  --search-service        AI Search service name       (.env: SEARCH_SERVICE_NAME)
  --cosmos-account        Cosmos DB account name       (.env: COSMOS_ACCOUNT_NAME)
  --env-file              Path to .env file            (default: <repo-root>/.env)
  --verbose, -v           Show detailed output
  --help, -h              Show this help

Examples:
  # Use .env defaults (no args needed if .env has all values):
  $(basename "$0")

  # Override specific values:
  $(basename "$0") -g rg-minion-dev-swe-003 -a ais-minion-dev-swc-hg2d -p aiproj-minion-dev-swc-hg2d

  # Full check with all resources:
  $(basename "$0") --storage-account stminiondevswe003 --search-service srch-minion-dev-swe-003
EOF
    exit 0
}

# --- Parse arguments (CLI overrides .env) ---
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-}"
ACCOUNT_NAME="${AI_FOUNDRY_HUB_NAME:-}"
PROJECT_NAME="${AI_FOUNDRY_PROJECT_NAME:-}"
SUBSCRIPTION_ID=""
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT_NAME:-}"
SEARCH_SERVICE="${SEARCH_SERVICE_NAME:-}"
COSMOS_ACCOUNT="${COSMOS_ACCOUNT_NAME:-}"
VERBOSE=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --resource-group|-g) RESOURCE_GROUP="$2"; shift ;;
        --account-name|-a) ACCOUNT_NAME="$2"; shift ;;
        --project-name|-p) PROJECT_NAME="$2"; shift ;;
        --subscription-id|-s) SUBSCRIPTION_ID="$2"; shift ;;
        --storage-account) STORAGE_ACCOUNT="$2"; shift ;;
        --search-service) SEARCH_SERVICE="$2"; shift ;;
        --cosmos-account) COSMOS_ACCOUNT="$2"; shift ;;
        --env-file) ;; # already handled above via ENV_FILE
        --verbose|-v) VERBOSE=true ;;
        --help|-h) usage ;;
        *) echo -e "${RED}Unknown parameter: $1${NC}"; usage ;;
    esac
    shift
done

# --- Validate required params ---
if [[ -z "$RESOURCE_GROUP" || -z "$ACCOUNT_NAME" || -z "$PROJECT_NAME" ]]; then
    echo -e "${RED}Error: --resource-group, --account-name, and --project-name are required (or set in .env).${NC}"
    echo -e "${YELLOW}Looked for .env at: $ENV_FILE${NC}"
    usage
fi

# --- Get subscription ID if not provided ---
if [[ -z "$SUBSCRIPTION_ID" ]]; then
    SUBSCRIPTION_ID=$(az account show --query id -o tsv)
    echo -e "${YELLOW}Using current subscription: $SUBSCRIPTION_ID${NC}"
fi

# --- Helper functions ---
print_header() {
    echo ""
    echo "============================================================================="
    echo -e " $1"
    echo "============================================================================="
}

check_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "  ${RED}✗${NC} $1"
}

check_warn() {
    echo -e "  ${YELLOW}!${NC} $1"
}

# Track overall status
ERRORS=0

# =============================================================================
# 1. CAPABILITY HOSTS
# =============================================================================
print_header "Capability Hosts"

echo ""
echo "  Checking account-level capability host..."
ACCOUNT_CAPHOST=$(az rest --method get --uri \
    "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME/capabilityHosts?api-version=$API_VERSION" \
    2>/dev/null || echo "ERROR")

if [[ "$ACCOUNT_CAPHOST" == "ERROR" ]]; then
    check_fail "Account capability host: FAILED to query"
    ((ERRORS++))
else
    ACCOUNT_CAPHOST_COUNT=$(echo "$ACCOUNT_CAPHOST" | python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data.get('value',[])))" 2>/dev/null || echo "0")
    if [[ "$ACCOUNT_CAPHOST_COUNT" -gt 0 ]]; then
        ACCOUNT_CAPHOST_STATE=$(echo "$ACCOUNT_CAPHOST" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['value'][0].get('properties',{}).get('provisioningState','Unknown'))" 2>/dev/null || echo "Unknown")
        if [[ "$ACCOUNT_CAPHOST_STATE" == "Succeeded" ]]; then
            check_pass "Account capability host: Provisioned (${ACCOUNT_CAPHOST_STATE})"
        else
            check_warn "Account capability host: State=${ACCOUNT_CAPHOST_STATE}"
        fi
    else
        check_fail "Account capability host: NOT FOUND"
        ((ERRORS++))
    fi
    if [[ "$VERBOSE" == true ]]; then
        echo "$ACCOUNT_CAPHOST" | python3 -m json.tool 2>/dev/null || echo "$ACCOUNT_CAPHOST"
    fi
fi

echo ""
echo "  Checking project-level capability host..."
PROJECT_CAPHOST=$(az rest --method get --uri \
    "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME/projects/$PROJECT_NAME/capabilityHosts?api-version=$API_VERSION" \
    2>/dev/null || echo "ERROR")

if [[ "$PROJECT_CAPHOST" == "ERROR" ]]; then
    check_fail "Project capability host: FAILED to query"
    ((ERRORS++))
else
    PROJECT_CAPHOST_COUNT=$(echo "$PROJECT_CAPHOST" | python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data.get('value',[])))" 2>/dev/null || echo "0")
    if [[ "$PROJECT_CAPHOST_COUNT" -gt 0 ]]; then
        PROJECT_CAPHOST_STATE=$(echo "$PROJECT_CAPHOST" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data['value'][0].get('properties',{}).get('provisioningState','Unknown'))" 2>/dev/null || echo "Unknown")
        if [[ "$PROJECT_CAPHOST_STATE" == "Succeeded" ]]; then
            check_pass "Project capability host: Provisioned (${PROJECT_CAPHOST_STATE})"
        else
            check_warn "Project capability host: State=${PROJECT_CAPHOST_STATE}"
        fi
    else
        check_fail "Project capability host: NOT FOUND"
        ((ERRORS++))
    fi
    if [[ "$VERBOSE" == true ]]; then
        echo "$PROJECT_CAPHOST" | python3 -m json.tool 2>/dev/null || echo "$PROJECT_CAPHOST"
    fi
fi

# =============================================================================
# 2. PROJECT MANAGED IDENTITY
# =============================================================================
print_header "Project Managed Identity"

echo ""
echo "  Retrieving project identity..."
PROJECT_IDENTITY=$(az rest --method get --uri \
    "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME/projects/$PROJECT_NAME?api-version=$API_VERSION" \
    2>/dev/null || echo "ERROR")

if [[ "$PROJECT_IDENTITY" == "ERROR" ]]; then
    check_fail "Could not retrieve project resource"
    ((ERRORS++))
    PROJECT_PRINCIPAL_ID=""
else
    PROJECT_PRINCIPAL_ID=$(echo "$PROJECT_IDENTITY" | python3 -c "import sys,json; data=json.load(sys.stdin); print(data.get('identity',{}).get('principalId',''))" 2>/dev/null || echo "")
    if [[ -n "$PROJECT_PRINCIPAL_ID" ]]; then
        check_pass "Project system-assigned identity: $PROJECT_PRINCIPAL_ID"
    else
        check_fail "Project has NO system-assigned managed identity"
        ((ERRORS++))
    fi
fi

# =============================================================================
# 3. IAM ROLE ASSIGNMENTS
# =============================================================================
print_header "IAM Role Assignments for Project Identity"

if [[ -z "$PROJECT_PRINCIPAL_ID" ]]; then
    check_warn "Skipping IAM checks — no project identity found"
else
    # --- Required roles on the AI Services account ---
    echo ""
    echo "  [AI Services Account: $ACCOUNT_NAME]"
    ACCOUNT_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$ACCOUNT_NAME"

    ACCOUNT_ROLES=$(az role assignment list --assignee "$PROJECT_PRINCIPAL_ID" --scope "$ACCOUNT_SCOPE" --query "[].roleDefinitionName" -o tsv 2>/dev/null || echo "")

    REQUIRED_ACCOUNT_ROLES=("Cognitive Services OpenAI Contributor" "Cognitive Services User")
    for role in "${REQUIRED_ACCOUNT_ROLES[@]}"; do
        if echo "$ACCOUNT_ROLES" | grep -qi "$role"; then
            check_pass "$role"
        else
            check_fail "$role — NOT ASSIGNED"
            ((ERRORS++))
        fi
    done

    # --- Storage account roles ---
    if [[ -n "$STORAGE_ACCOUNT" ]]; then
        echo ""
        echo "  [Storage Account: $STORAGE_ACCOUNT]"
        STORAGE_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"
        STORAGE_ROLES=$(az role assignment list --assignee "$PROJECT_PRINCIPAL_ID" --scope "$STORAGE_SCOPE" --query "[].roleDefinitionName" -o tsv 2>/dev/null || echo "")

        REQUIRED_STORAGE_ROLES=("Storage Blob Data Contributor")
        for role in "${REQUIRED_STORAGE_ROLES[@]}"; do
            if echo "$STORAGE_ROLES" | grep -qi "$role"; then
                check_pass "$role"
            else
                check_fail "$role — NOT ASSIGNED"
                ((ERRORS++))
            fi
        done
    fi

    # --- AI Search roles ---
    if [[ -n "$SEARCH_SERVICE" ]]; then
        echo ""
        echo "  [AI Search: $SEARCH_SERVICE]"
        SEARCH_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Search/searchServices/$SEARCH_SERVICE"
        SEARCH_ROLES=$(az role assignment list --assignee "$PROJECT_PRINCIPAL_ID" --scope "$SEARCH_SCOPE" --query "[].roleDefinitionName" -o tsv 2>/dev/null || echo "")

        REQUIRED_SEARCH_ROLES=("Search Index Data Contributor" "Search Service Contributor")
        for role in "${REQUIRED_SEARCH_ROLES[@]}"; do
            if echo "$SEARCH_ROLES" | grep -qi "$role"; then
                check_pass "$role"
            else
                check_fail "$role — NOT ASSIGNED"
                ((ERRORS++))
            fi
        done
    fi

    # --- Cosmos DB roles ---
    if [[ -n "$COSMOS_ACCOUNT" ]]; then
        echo ""
        echo "  [Cosmos DB: $COSMOS_ACCOUNT]"
        COSMOS_SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$COSMOS_ACCOUNT"
        COSMOS_ROLES=$(az role assignment list --assignee "$PROJECT_PRINCIPAL_ID" --scope "$COSMOS_SCOPE" --query "[].roleDefinitionName" -o tsv 2>/dev/null || echo "")

        REQUIRED_COSMOS_ROLES=("Cosmos DB Operator")
        for role in "${REQUIRED_COSMOS_ROLES[@]}"; do
            if echo "$COSMOS_ROLES" | grep -qi "$role"; then
                check_pass "$role"
            else
                check_fail "$role — NOT ASSIGNED"
                ((ERRORS++))
            fi
        done

        # Check Cosmos DB data-plane role assignments (SQL role assignments)
        echo "  Checking Cosmos DB data-plane SQL role assignments..."
        COSMOS_SQL_ROLES=$(az cosmosdb sql role assignment list --account-name "$COSMOS_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query "[?principalId=='$PROJECT_PRINCIPAL_ID'].roleDefinitionId" -o tsv 2>/dev/null || echo "")
        if [[ -n "$COSMOS_SQL_ROLES" ]]; then
            check_pass "Cosmos DB SQL data-plane role assigned"
        else
            check_warn "Cosmos DB SQL data-plane role: not found (may use account-level access)"
        fi
    fi
fi

# =============================================================================
# 4. AUTO-DISCOVER RESOURCES (if not provided)
# =============================================================================
if [[ -z "$STORAGE_ACCOUNT" && -z "$SEARCH_SERVICE" && -z "$COSMOS_ACCOUNT" ]]; then
    print_header "Auto-discovered Resources (for reference)"
    echo ""
    echo "  Discovering resources in $RESOURCE_GROUP..."

    DISCOVERED_STORAGE=$(az storage account list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
    DISCOVERED_SEARCH=$(az search service list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")
    DISCOVERED_COSMOS=$(az cosmosdb list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || echo "")

    [[ -n "$DISCOVERED_STORAGE" ]] && echo "  Storage Account: $DISCOVERED_STORAGE" || echo "  Storage Account: (none found)"
    [[ -n "$DISCOVERED_SEARCH" ]] && echo "  AI Search:       $DISCOVERED_SEARCH" || echo "  AI Search:       (none found)"
    [[ -n "$DISCOVERED_COSMOS" ]] && echo "  Cosmos DB:       $DISCOVERED_COSMOS" || echo "  Cosmos DB:       (none found)"

    echo ""
    echo "  Tip: Re-run with --storage-account, --search-service, --cosmos-account to check IAM on these."
fi

# =============================================================================
# SUMMARY
# =============================================================================
print_header "Summary"
echo ""
if [[ $ERRORS -eq 0 ]]; then
    echo -e "  ${GREEN}All checks passed!${NC}"
else
    echo -e "  ${RED}$ERRORS issue(s) found.${NC} Review the output above."
fi
echo ""

exit $ERRORS