<#
.SYNOPSIS
  Uploads sample documents to Azure Blob Storage for AI Search connectivity testing.

.DESCRIPTION
  Creates and uploads small text documents to the 'search-sample-data' container
  in the designated storage account. Uses Azure AD authentication (no shared keys).
  
  Prerequisites:
  - Azure CLI installed and logged in (az login)
  - Storage Blob Data Contributor role on the storage account for the current user
  - Public network access enabled on the storage account (or VPN/private access)

.PARAMETER ResourceGroup
  Resource group containing the storage account.

.PARAMETER StorageAccountName
  Name of the storage account (e.g., stminiondevswchg2d).

.PARAMETER ContainerName
  Blob container name for sample data. Default: search-sample-data.

.EXAMPLE
  .\upload-search-sample-data.ps1 -ResourceGroup "rg-minion-dev-swe-002" -StorageAccountName "stminiondevswchg2d"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$StorageAccountName,

    [Parameter()]
    [string]$ContainerName = "search-sample-data"
)

$ErrorActionPreference = "Stop"

Write-Host "=== AI Search Sample Data Upload ===" -ForegroundColor Cyan
Write-Host "Storage Account: $StorageAccountName"
Write-Host "Container: $ContainerName"
Write-Host ""

# Create temp directory for sample documents
$tempDir = Join-Path $env:TEMP "search-sample-data-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

# Generate sample documents that will trigger AI enrichment skills
$documents = @{
    "doc1-ai-agents.txt" = @"
Azure AI Agent Service enables developers to build, deploy, and scale AI agents securely.
Agents can leverage tools like code interpreter, file search, and custom functions.
The service supports network isolation with private endpoints and managed identities.
Key benefits include automatic scaling, built-in monitoring, and enterprise-grade security.
"@

    "doc2-foundry-platform.txt" = @"
Microsoft Foundry provides a unified platform for AI application development.
It combines model management, prompt engineering, evaluation, and deployment capabilities.
Teams can collaborate on AI projects with role-based access control and shared resources.
The platform integrates with Azure AI Search for retrieval-augmented generation patterns.
"@

    "doc3-vector-search.txt" = @"
Векторный поиск — это подход к получению информации, поддерживающий индексирование и запросы по числовым представлениям содержимого. Так как содержимое является числовым, а не обычным текстом, сопоставление основано на векторах, которые наиболее похожи на вектор запроса. Этот подход обеспечивает сопоставление между следующими элементами:
Семантическое или концептуальное сходство. Например, "собака" и "кейн" концептуально похожи, но лингвистически отличаются.
Многоязычное содержимое, например "собака" на английском языке и "hund" на немецком языке.
Несколько типов контента, таких как "собака" в виде обычного текста и изображение собаки.
"@

    "doc4-network-security.txt" = @"
Network isolation is critical for enterprise AI deployments handling sensitive data.
Private endpoints ensure traffic stays on the Microsoft backbone network.
Managed identities eliminate the need for stored credentials and API keys.
Azure Policy can enforce network restrictions across all AI services in a subscription.
"@

    "doc5-responsible-ai.txt" = @"
Responsible AI practices include fairness, reliability, privacy, and transparency.
Content filtering in Azure AI Services helps prevent harmful outputs.
Regular evaluation and monitoring detect model drift and quality degradation.
Organizations should establish governance frameworks before deploying AI at scale.
"@
}

Write-Host "Creating $($documents.Count) sample documents..." -ForegroundColor Yellow

foreach ($fileName in $documents.Keys) {
    $filePath = Join-Path $tempDir $fileName
    $documents[$fileName] | Out-File -FilePath $filePath -Encoding utf8
    Write-Host "  Created: $fileName"
}

Write-Host ""
Write-Host "Uploading to container '$ContainerName'..." -ForegroundColor Yellow

# Upload using AAD auth (no shared keys)
az storage blob upload-batch `
    --destination $ContainerName `
    --source $tempDir `
    --account-name $StorageAccountName `
    --auth-mode login `
    --overwrite $true

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Upload failed. Ensure:" -ForegroundColor Red
    Write-Host "  1. You have 'Storage Blob Data Contributor' role on the storage account" -ForegroundColor Red
    Write-Host "  2. Public network access is enabled (or you're on the private network)" -ForegroundColor Red
    Write-Host "  3. The container '$ContainerName' exists (deploy search-pipeline module first)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Upload complete! Verifying..." -ForegroundColor Green

# List uploaded blobs
az storage blob list `
    --container-name $ContainerName `
    --account-name $StorageAccountName `
    --auth-mode login `
    --output table `
    --query "[].{Name:name, Size:properties.contentLength}"

# Cleanup temp files
Remove-Item -Path $tempDir -Recurse -Force

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Next step: Deploy the search-pipeline Bicep module, then run validate-search-pipeline.ps1"
