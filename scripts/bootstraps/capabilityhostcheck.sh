
#!/bin/bash

subscriptionId="d499a328-d498-40e0-8882-2e0a1eb904d2"
resourceGroupName="rg-minion-dev-swe-003"
accountName="ais-minion-dev-swc-hg2d"
projectName="aiproj-minion-dev-swc-hg2d"
# Account-level capability host
az rest --method get --uri \
"https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroupName/providers/Microsoft.CognitiveServices/accounts/$accountName/capabilityHosts?api-version=2025-04-01-preview"

# Project-level capability host
az rest --method get --uri \
"https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroupName/providers/Microsoft.CognitiveServices/accounts/$accountName/projects/$projectName/capabilityHosts?api-version=2025-04-01-preview"


az cosmosdb sql database list \
  --account-name cosmos-minion-dev-swc-hg2d \
  --resource-group rg-minion-dev-swe-003 \
  --query "[].id" -o tsv