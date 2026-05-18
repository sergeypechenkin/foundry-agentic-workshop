az login

$RESOURCE_GROUP="rg-minion-dev-swe-003"
$LOCATION="swedencentral"
$Suffix="hg2d" # Change this suffix for unique resource names if deploying multiple times to same region
$token = az account get-access-token --resource "https://management.azure.com" --query accessToken -o tsv



az group create --name $RESOURCE_GROUP --location $LOCATION --tags SecurityControl=ignore

# Pre-deploy: purge any soft-deleted cognitive services in this location to avoid conflicts
$deleted = az cognitiveservices account list-deleted --query "[?location=='$LOCATION'].name" -o tsv
$deleted
if ($deleted) {
  foreach ($name in $deleted) {
    Write-Host "Purging soft-deleted cognitive services account: $name"
    az cognitiveservices account purge --name $name --resource-group $RESOURCE_GROUP --location $LOCATION
  }
}

# What-if preview (shows changes without deploying)
az deployment group what-if `
  --resource-group $RESOURCE_GROUP `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam

# Actual deployment (uncomment when ready)
az deployment group create `
  --resource-group $RESOURCE_GROUP `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam

#az group delete --name $RESOURCE_GROUP --yes --no-wait

# ========================
# CLEANUP (run after RG delete completes)
# ========================
# Purge soft-deleted cognitive services accounts to avoid conflicts on next deploy
# az cognitiveservices account list-deleted --query "[?location=='$LOCATION'].name" -o tsv | ForEach-Object {
#   Write-Host "Purging soft-deleted account: $_"
#   az cognitiveservices account purge --name $_ --resource-group $RESOURCE_GROUP --location $LOCATION
# }



$uri = "https://management.azure.com/subscriptions/d499a328-d498-40e0-8882-2e0a1eb904d2/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/ais-minion-dev-swc-$Suffix`?api-version=2025-04-01-preview"
$body = '{"properties": {"publicNetworkAccess": "Enabled", "networkAcls": {"defaultAction": "Allow"}}}'

# Enable Public Network after deployment
Invoke-RestMethod -Method PATCH -Uri $uri `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body $body

# AI Search
az search service update --name "srch-minion-dev-swc-$Suffix" -g $RESOURCE_GROUP `
  --public-network-access enabled `
  --default-action Allow

# Storage
az storage account update --name "stminiondevswc$Suffix" -g $RESOURCE_GROUP `
  --public-network-access enabled `
  --default-action Allow

# Cosmos DB
az cosmosdb update --name "cosmos-minion-dev-swc-$Suffix" -g $RESOURCE_GROUP `
  --enable-public-network true `
  --default-action Allow