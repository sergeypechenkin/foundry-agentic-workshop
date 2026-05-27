// Creates Azure AI Search pipeline prerequisites (blob container + role assignments).
// The actual Search components (index, data source, skillset, indexer) are NOT ARM resources
// and must be created via the Search REST API — see scripts/bootstraps/create-search-pipeline.ps1

@description('Name of the AI Search service')
param aiSearchName string

@description('Name of the storage account containing sample data')
param storageName string

@description('Name of the Foundry AI Services account')
param aiServicesAccountName string

@description('Resource ID of the Foundry AI Services account')
param aiServicesAccountResourceId string

@description('Subscription ID where the storage account is located')
param storageSubscriptionId string = subscription().subscriptionId

@description('Resource group where the storage account is located')
param storageResourceGroupName string = resourceGroup().name

@description('Name of the blob container with sample data')
param sampleDataContainerName string = 'search-sample-data'

// Reference existing AI Search service
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = {
  name: aiSearchName
}

// Reference existing storage account (cross-subscription support)
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageName
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
}

// --- Blob container for sample data ---
module sampleDataContainer 'search-sample-data-container.bicep' = {
  name: 'search-sample-data-container-deployment'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    storageName: storageName
    containerName: sampleDataContainerName
  }
}

// --- Role assignments for AI Search managed identity ---
module searchRoleAssignments 'search-pipeline-role-assignments.bicep' = {
  name: 'search-pipeline-role-assignments-deployment'
  params: {
    storageName: storageName
    storageSubscriptionId: storageSubscriptionId
    storageResourceGroupName: storageResourceGroupName
    aiServicesAccountName: aiServicesAccountName
    searchServicePrincipalId: searchService.identity.principalId
  }
}

output aiSearchName string = aiSearchName
output storageResourceId string = storageAccount.id
output aiServicesAccountResourceId string = aiServicesAccountResourceId
output sampleDataContainerName string = sampleDataContainerName
