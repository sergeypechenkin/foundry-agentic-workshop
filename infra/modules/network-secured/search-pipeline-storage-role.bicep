// Assigns Storage Blob Data Reader role to AI Search managed identity
// Scoped to the storage account for indexer blob access

@description('Name of the storage account')
param storageName string

@description('Principal ID of the AI Search system-assigned managed identity')
param searchServicePrincipalId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageName
}

// Storage Blob Data Reader
resource storageBlobDataReaderRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  scope: resourceGroup()
}

resource storageBlobDataReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storageAccount
  name: guid(searchServicePrincipalId, storageBlobDataReaderRole.id, storageAccount.id)
  properties: {
    principalId: searchServicePrincipalId
    roleDefinitionId: storageBlobDataReaderRole.id
    principalType: 'ServicePrincipal'
  }
}
