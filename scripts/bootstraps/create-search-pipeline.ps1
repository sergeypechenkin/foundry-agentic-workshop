<#
.SYNOPSIS
  Creates AI Search pipeline components (index, data source, skillset, indexer) via REST API.

.DESCRIPTION
  AI Search sub-resources (indexes, data sources, skillsets, indexers) are NOT ARM resources
  and cannot be deployed via Bicep. This script creates them using the Search REST API.
  
  Prerequisites:
  - Bicep deployment completed (creates container + role assignments)
  - Azure CLI logged in
  - Public network access enabled on AI Search (or private network access)

.PARAMETER ResourceGroup
  Resource group containing the AI Search service.

.PARAMETER SearchServiceName
  Name of the AI Search service (e.g., srch-minion-dev-swc-hg2d).

.PARAMETER StorageAccountResourceId
  Full ARM resource ID of the storage account.

.PARAMETER AiServicesResourceId
  Full ARM resource ID of the Foundry AI Services account.

.PARAMETER ContainerName
  Blob container name with sample data. Default: search-sample-data.

.EXAMPLE
  .\create-search-pipeline.ps1 `
    -ResourceGroup "rg-minion-dev-swe-003" `
    -SearchServiceName "srch-minion-dev-swc-hg2d" `
    -StorageAccountResourceId "/subscriptions/.../storageAccounts/stminiondevswchg2d" `
    -AiServicesResourceId "/subscriptions/.../accounts/ais-minion-dev-swc-hg2d"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$SearchServiceName,

    [Parameter(Mandatory = $true)]
    [string]$StorageAccountResourceId,

    [Parameter(Mandatory = $true)]
    [string]$AiServicesResourceId,

    [Parameter()]
    [string]$ContainerName = "search-sample-data"
)

$ErrorActionPreference = "Stop"
$apiVersion = "2024-07-01"
$previewApiVersion = "2025-05-01-preview"
$searchEndpoint = "https://$SearchServiceName.search.windows.net"

Write-Host "=== Create AI Search Pipeline ===" -ForegroundColor Cyan
Write-Host "Search Service: $SearchServiceName"
Write-Host "Storage: $StorageAccountResourceId"
Write-Host "AI Services: $AiServicesResourceId"
Write-Host ""

# Get admin key for Search REST API
$adminKey = az search admin-key show `
    --service-name $SearchServiceName `
    --resource-group $ResourceGroup `
    --query primaryKey -o tsv

if (-not $adminKey) {
    Write-Host "ERROR: Failed to get admin key. Ensure you have access to the Search service." -ForegroundColor Red
    exit 1
}

$headers = @{
    "api-key"      = $adminKey
    "Content-Type" = "application/json"
}

function Invoke-SearchApi {
    param(
        [string]$Method,
        [string]$Path,
        [string]$Body,
        [string]$ApiVer = $apiVersion
    )
    $uri = "$searchEndpoint/$Path`?api-version=$ApiVer"
    try {
        $response = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $Body
        return $response
    }
    catch {
        $errorResponse = $_.ErrorDetails.Message
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        if ($errorResponse) {
            Write-Host "Details: $errorResponse" -ForegroundColor Red
        }
        throw
    }
}

# --- 1. Create Index ---
Write-Host "[1/4] Creating index 'sample-connectivity-index'..." -ForegroundColor Yellow

$indexBody = @{
    name = "sample-connectivity-index"
    fields = @(
        @{ name = "id"; type = "Edm.String"; key = $true; filterable = $true; retrievable = $true }
        @{ name = "content"; type = "Edm.String"; searchable = $true; retrievable = $true }
        @{ name = "metadata_storage_path"; type = "Edm.String"; filterable = $true; retrievable = $true }
        @{ name = "metadata_storage_name"; type = "Edm.String"; filterable = $true; retrievable = $true }
        @{ name = "keyphrases"; type = "Collection(Edm.String)"; searchable = $true; filterable = $true; retrievable = $true }
        @{ name = "language"; type = "Edm.String"; filterable = $true; retrievable = $true }
        @{
            name = "content_vector"
            type = "Collection(Edm.Single)"
            searchable = $true
            retrievable = $true
            dimensions = 1536
            vectorSearchProfile = "default-vector-profile"
        }
        @{ name = "summary"; type = "Edm.String"; searchable = $true; retrievable = $true }
    )
    vectorSearch = @{
        algorithms = @(
            @{
                name = "default-hnsw"
                kind = "hnsw"
                hnswParameters = @{
                    m = 4
                    efConstruction = 400
                    efSearch = 500
                    metric = "cosine"
                }
            }
        )
        profiles = @(
            @{
                name = "default-vector-profile"
                algorithm = "default-hnsw"
            }
        )
    }
} | ConvertTo-Json -Depth 10

Invoke-SearchApi -Method PUT -Path "indexes/sample-connectivity-index" -Body $indexBody
Write-Host "  Index created." -ForegroundColor Green

# --- 2. Create Data Source ---
Write-Host "[2/4] Creating data source 'sample-blob-datasource'..." -ForegroundColor Yellow

$dataSourceBody = @{
    name = "sample-blob-datasource"
    type = "azureblob"
    credentials = @{
        connectionString = "ResourceId=$StorageAccountResourceId;"
    }
    container = @{
        name = $ContainerName
    }
} | ConvertTo-Json -Depth 10

Invoke-SearchApi -Method PUT -Path "datasources/sample-blob-datasource" -Body $dataSourceBody
Write-Host "  Data source created." -ForegroundColor Green

# --- 3. Create Skillset ---
Write-Host "[3/4] Creating skillset 'sample-connectivity-skillset'..." -ForegroundColor Yellow

# Extract account name from resource ID for subdomain URL
$aiServicesAccountName = ($AiServicesResourceId -split '/')[-1]
$subdomainUrl = "https://$aiServicesAccountName.cognitiveservices.azure.com"
$openaiResourceUri = "https://$aiServicesAccountName.openai.azure.com"

$skillsetBody = @{
    name = "sample-connectivity-skillset"
    description = "Skillset to validate AI Search to Foundry AI Services connectivity (built-in skills + OpenAI models)"
    cognitiveServices = @{
        "@odata.type" = "#Microsoft.Azure.Search.AIServicesByIdentity"
        subdomainUrl = $subdomainUrl
        identity = $null
    }
    skills = @(
        @{
            "@odata.type" = "#Microsoft.Skills.Text.KeyPhraseExtractionSkill"
            name = "keyphraseExtraction"
            description = "Extracts key phrases (validates Text Analytics via AI Services)"
            context = "/document"
            inputs = @(
                @{ name = "text"; source = "/document/content" }
            )
            outputs = @(
                @{ name = "keyPhrases"; targetName = "keyphrases" }
            )
        }
        @{
            "@odata.type" = "#Microsoft.Skills.Text.LanguageDetectionSkill"
            name = "languageDetection"
            description = "Detects language (validates Text Analytics via AI Services)"
            context = "/document"
            inputs = @(
                @{ name = "text"; source = "/document/content" }
            )
            outputs = @(
                @{ name = "languageCode"; targetName = "language" }
            )
        }
        @{
            "@odata.type" = "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill"
            name = "embeddingSkill"
            description = "Generates vector embeddings (validates OpenAI model connectivity)"
            context = "/document"
            inputs = @(
                @{ name = "text"; source = "/document/content" }
            )
            outputs = @(
                @{ name = "embedding"; targetName = "content_vector" }
            )
            resourceUri = $openaiResourceUri
            deploymentId = "text-embedding-3-small"
            modelName = "text-embedding-3-small"
        }
        @{
            "@odata.type" = "#Microsoft.Skills.Custom.ChatCompletionSkill"
            name = "summarizationSkill"
            description = "Generates a text summary (validates OpenAI chat completion model connectivity)"
            context = "/document"
            uri = "$openaiResourceUri/openai/deployments/gpt-4.1/chat/completions?api-version=2024-06-01"
            timeout = "PT30S"
            degreeOfParallelism = 1
            authResourceId = "https://cognitiveservices.azure.com"
            inputs = @(
                @{ name = "systemMessage"; source = "= 'Summarize the following document in 2-3 concise sentences.'" }
                @{ name = "userMessage"; source = "/document/content" }
            )
            outputs = @(
                @{ name = "response"; targetName = "summary" }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-SearchApi -Method PUT -Path "skillsets/sample-connectivity-skillset" -Body $skillsetBody -ApiVer $previewApiVersion
Write-Host "  Skillset created." -ForegroundColor Green

# --- 4. Create Indexer ---
Write-Host "[4/4] Creating indexer 'sample-connectivity-indexer'..." -ForegroundColor Yellow

$indexerBody = @{
    name = "sample-connectivity-indexer"
    description = "Indexer to validate end-to-end connectivity (Storage -> AI Search -> AI Services) via private endpoints"
    dataSourceName = "sample-blob-datasource"
    targetIndexName = "sample-connectivity-index"
    skillsetName = "sample-connectivity-skillset"
    fieldMappings = @(
        @{
            sourceFieldName = "metadata_storage_path"
            targetFieldName = "id"
            mappingFunction = @{ name = "base64Encode" }
        }
        @{
            sourceFieldName = "metadata_storage_path"
            targetFieldName = "metadata_storage_path"
        }
        @{
            sourceFieldName = "metadata_storage_name"
            targetFieldName = "metadata_storage_name"
        }
    )
    outputFieldMappings = @(
        @{
            sourceFieldName = "/document/keyphrases"
            targetFieldName = "keyphrases"
        }
        @{
            sourceFieldName = "/document/language"
            targetFieldName = "language"
        }
        @{
            sourceFieldName = "/document/content_vector"
            targetFieldName = "content_vector"
        }
        @{
            sourceFieldName = "/document/summary"
            targetFieldName = "summary"
        }
    )
    parameters = @{
        configuration = @{
            executionEnvironment = "private"
            dataToExtract = "contentAndMetadata"
        }
    }
} | ConvertTo-Json -Depth 10

Invoke-SearchApi -Method PUT -Path "indexers/sample-connectivity-indexer" -Body $indexerBody -ApiVer $previewApiVersion
Write-Host "  Indexer created." -ForegroundColor Green

Write-Host ""
Write-Host "=== Pipeline Created Successfully ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Upload sample data:  .\upload-search-sample-data.ps1 -ResourceGroup $ResourceGroup -StorageAccountName <name>"
Write-Host "  2. Run indexer:         az search indexer run --name sample-connectivity-indexer --service-name $SearchServiceName -g $ResourceGroup"
Write-Host "  3. Validate:            .\validate-search-pipeline.ps1 -ResourceGroup $ResourceGroup -SearchServiceName $SearchServiceName"
