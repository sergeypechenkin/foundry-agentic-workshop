// Role assignments required for the AI Search pipeline:
// 1. AI Search → Storage: Storage Blob Data Reader (for indexer to read blobs)
// 2. AI Search → AI Services: Cognitive Services User (for skillset execution)

@description('Name of the storage account')
param storageName string

@description('Subscription ID of the storage account')
param storageSubscriptionId string = subscription().subscriptionId

@description('Resource group of the storage account')
param storageResourceGroupName string = resourceGroup().name

@description('Name of the Foundry AI Services account')
param aiServicesAccountName string

@description('Principal ID of the AI Search system-assigned managed identity')
param searchServicePrincipalId string

// --- Storage Blob Data Reader for AI Search MI ---
// Role ID: 2a2b9908-6ea1-4ae2-8e65-a410df84e7d1
module storageBlobReaderForSearch 'search-pipeline-storage-role.bicep' = {
  name: 'search-pipeline-storage-blob-reader'
  scope: resourceGroup(storageSubscriptionId, storageResourceGroupName)
  params: {
    storageName: storageName
    searchServicePrincipalId: searchServicePrincipalId
  }
}

// --- Cognitive Services User for AI Search MI ---
// Role ID: a97b65f3-24c7-4388-baec-2e87135dc908
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesAccountName
}

resource cognitiveServicesUserRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  scope: resourceGroup()
}

resource cognitiveServicesUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiServices
  name: guid(searchServicePrincipalId, cognitiveServicesUserRole.id, aiServices.id)
  properties: {
    principalId: searchServicePrincipalId
    roleDefinitionId: cognitiveServicesUserRole.id
    principalType: 'ServicePrincipal'
  }
}
