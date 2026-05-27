<#
.SYNOPSIS
  Validates AI Search pipeline connectivity by running the indexer and checking results.

.DESCRIPTION
  Triggers the AI Search indexer, waits for completion, and verifies that:
  1. The indexer ran successfully (validates Storage → AI Search connectivity via PE)
  2. Enrichment skills executed (validates AI Search → Foundry AI Services connectivity via PE)
  3. Documents are indexed with enriched fields (keyphrases, language)

.PARAMETER ResourceGroup
  Resource group containing the AI Search service.

.PARAMETER SearchServiceName
  Name of the AI Search service (e.g., srch-minion-dev-swc-hg2d).

.PARAMETER IndexerName
  Name of the indexer to run. Default: sample-connectivity-indexer.

.PARAMETER IndexName
  Name of the index to query. Default: sample-connectivity-index.

.EXAMPLE
  .\validate-search-pipeline.ps1 -ResourceGroup "rg-minion-dev-swe-002" -SearchServiceName "srch-minion-dev-swc-hg2d"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$SearchServiceName,

    [Parameter()]
    [string]$IndexerName = "sample-connectivity-indexer",

    [Parameter()]
    [string]$IndexName = "sample-connectivity-index"
)

$ErrorActionPreference = "Stop"

$apiVersion = "2025-05-01-preview"
$searchEndpoint = "https://$SearchServiceName.search.windows.net"

Write-Host "=== AI Search Pipeline Validation ===" -ForegroundColor Cyan
Write-Host "Search Service: $SearchServiceName"
Write-Host "Indexer: $IndexerName"
Write-Host "Index: $IndexName"
Write-Host ""

# Get admin key for REST API calls
$adminKey = az search admin-key show `
    --service-name $SearchServiceName `
    --resource-group $ResourceGroup `
    --query primaryKey -o tsv 2>&1

if ($LASTEXITCODE -ne 0 -or -not $adminKey) {
    Write-Host "ERROR: Failed to get admin key." -ForegroundColor Red
    Write-Host "  Details: $adminKey" -ForegroundColor Red
    Write-Host ""
    Write-Host "  HINT: Ensure AI Search public network access is enabled for management operations." -ForegroundColor Yellow
    Write-Host "  Run: az search service update --name $SearchServiceName -g $ResourceGroup --public-network-access enabled" -ForegroundColor Yellow
    exit 1
}

$headers = @{
    "api-key"      = $adminKey
    "Content-Type" = "application/json"
}

# Step 1: Reset indexer to force reprocessing all documents
Write-Host "[1/5] Resetting indexer '$IndexerName' (force full reprocessing)..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Method POST `
        -Uri "$searchEndpoint/indexers/$IndexerName/reset?api-version=$apiVersion" `
        -Headers $headers
    Write-Host "  Indexer reset successfully." -ForegroundColor Green
}
catch {
    $err = $_.ErrorDetails.Message
    $exception = $_.Exception.Message
    Write-Host "WARNING: Failed to reset indexer." -ForegroundColor DarkYellow
    if ($err) { Write-Host "  Details: $err" -ForegroundColor DarkYellow }
    elseif ($exception) { Write-Host "  Details: $exception" -ForegroundColor DarkYellow }
}

Write-Host ""

# Step 2: Run the indexer
Write-Host "[2/5] Running indexer '$IndexerName'..." -ForegroundColor Yellow
try {
    Invoke-RestMethod -Method POST `
        -Uri "$searchEndpoint/indexers/$IndexerName/run?api-version=$apiVersion" `
        -Headers $headers
    Write-Host "  Indexer triggered successfully." -ForegroundColor Green
}
catch {
    $err = $_.ErrorDetails.Message
    $exception = $_.Exception.Message
    Write-Host "ERROR: Failed to trigger indexer." -ForegroundColor Red
    if ($err) { Write-Host "  Details: $err" -ForegroundColor Red }
    elseif ($exception) { Write-Host "  Details: $exception" -ForegroundColor Red }
    if ($exception -match "No such host|actively refused|network|unreachable|403|public network access") {
        Write-Host ""
        Write-Host "  HINT: AI Search public network access may be disabled." -ForegroundColor Yellow
        Write-Host "  Run: az search service update --name $SearchServiceName -g $ResourceGroup --public-network-access enabled" -ForegroundColor Yellow
    }
    exit 1
}

Write-Host ""

# Step 3: Wait for indexer to complete
Write-Host "[3/5] Waiting for indexer to complete..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$completed = $false

while (-not $completed -and $attempt -lt $maxAttempts) {
    Start-Sleep -Seconds 10
    $attempt++

    try {
        $status = Invoke-RestMethod -Method GET `
            -Uri "$searchEndpoint/indexers/$IndexerName/status?api-version=$apiVersion" `
            -Headers $headers

        $lastResult = $status.lastResult

        if ($null -ne $lastResult) {
            $runStatus = $lastResult.status
            Write-Host "  Status: $runStatus (attempt $attempt/$maxAttempts)"

            if ($runStatus -eq "success" -or $runStatus -eq "transientFailure" -or $runStatus -eq "persistentFailure") {
                $completed = $true
            }
        }
    }
    catch {
        Write-Host "  Warning: Could not get indexer status (attempt $attempt/$maxAttempts)" -ForegroundColor DarkYellow
    }
}

if (-not $completed) {
    Write-Host "WARNING: Indexer did not complete within timeout. Check status manually." -ForegroundColor DarkYellow
}

Write-Host ""

# Step 4: Check indexer execution details
Write-Host "[4/5] Checking indexer execution details..." -ForegroundColor Yellow

try {
    $status = Invoke-RestMethod -Method GET `
        -Uri "$searchEndpoint/indexers/$IndexerName/status?api-version=$apiVersion" `
        -Headers $headers
}
catch {
    $exception = $_.Exception.Message
    Write-Host "ERROR: Failed to query indexer status." -ForegroundColor Red
    Write-Host "  Details: $exception" -ForegroundColor Red
    if ($exception -match "No such host|actively refused|network|unreachable|403|public network access") {
        Write-Host ""
        Write-Host "  HINT: AI Search public network access may be disabled." -ForegroundColor Yellow
        Write-Host "  Run: az search service update --name $SearchServiceName -g $ResourceGroup --public-network-access enabled" -ForegroundColor Yellow
    }
    exit 1
}

$lastResult = $status.lastResult

if ($null -eq $lastResult) {
    Write-Host "ERROR: No execution history found." -ForegroundColor Red
    exit 1
}

Write-Host "  Final Status: $($lastResult.status)"
Write-Host "  Items Processed: $($lastResult.itemsProcessed)"
Write-Host "  Items Failed: $($lastResult.itemsFailed)"
Write-Host "  Start Time: $($lastResult.startTime)"
Write-Host "  End Time: $($lastResult.endTime)"

if ($lastResult.status -ne "success") {
    Write-Host ""
    Write-Host "FAILURE DETAILS:" -ForegroundColor Red
    if ($lastResult.errors) {
        foreach ($err in $lastResult.errors) {
            Write-Host "  Error: $($err.message)" -ForegroundColor Red
            Write-Host "  Key: $($err.key)" -ForegroundColor Red
            if ($err.details) { Write-Host "  Details: $($err.details)" -ForegroundColor Red }
            Write-Host ""
        }
    }
    if ($lastResult.warnings) {
        foreach ($warning in $lastResult.warnings) {
            Write-Host "  Warning: $($warning.message)" -ForegroundColor DarkYellow
        }
    }
    if (-not $lastResult.errors -and -not $lastResult.warnings) {
        if ($lastResult.errorMessage) {
            Write-Host "  Error Message: $($lastResult.errorMessage)" -ForegroundColor Red
        } else {
            Write-Host "  No error or warning details returned by indexer." -ForegroundColor DarkYellow
        }
        if ($lastResult.statusMessage) {
            Write-Host "  Status message: $($lastResult.statusMessage)" -ForegroundColor DarkYellow
        }
    }
    exit 1
} else {
    # Show warnings even on success (e.g., per-document skill warnings)
    if ($lastResult.warnings) {
        Write-Host ""
        Write-Host "  Warnings ($($lastResult.warnings.Count)):" -ForegroundColor DarkYellow
        foreach ($warning in $lastResult.warnings | Select-Object -First 5) {
            Write-Host "    - $($warning.message)" -ForegroundColor DarkYellow
        }
    }
}

Write-Host ""

# Step 5: Query the index for enriched documents
Write-Host "[5/5] Querying index for enriched documents..." -ForegroundColor Yellow

$body = @{
    search = "*"
    select = "metadata_storage_name,keyphrases,language,content_vector,summary"
    count = $true
} | ConvertTo-Json

$response = Invoke-RestMethod -Method POST `
    -Uri "$searchEndpoint/indexes/$IndexName/docs/search?api-version=$apiVersion" `
    -Headers $headers -Body $body

$docCount = $response.'@odata.count'
Write-Host "  Documents in index: $docCount"
Write-Host ""

if ($docCount -eq 0) {
    Write-Host "ERROR: No documents found in index. Check indexer errors above." -ForegroundColor Red
    exit 1
}

# Display enrichment results
Write-Host "  Enrichment Results:" -ForegroundColor Green
Write-Host "  -------------------"

$allEnriched = $true
$hasEmbeddings = $true
$hasSummaries = $true
foreach ($doc in $response.value) {
    $name = $doc.metadata_storage_name
    $lang = $doc.language
    $phrases = if ($doc.keyphrases) { ($doc.keyphrases | Select-Object -First 3) -join ", " } else { "(none)" }
    $vectorDims = if ($doc.content_vector) { $doc.content_vector.Count } else { 0 }
    $summaryText = if ($doc.summary) { $doc.summary.Substring(0, [Math]::Min(120, $doc.summary.Length)) + "..." } else { "(none)" }
    
    Write-Host "  File: $name"
    Write-Host "    Language: $lang"
    Write-Host "    Key Phrases: $phrases"
    Write-Host "    Vector dims: $vectorDims"
    Write-Host "    Summary: $summaryText"
    Write-Host ""

    if (-not $lang -or -not $doc.keyphrases) {
        $allEnriched = $false
    }
    if (-not $doc.content_vector -or $doc.content_vector.Count -eq 0) {
        $hasEmbeddings = $false
    }
    if (-not $doc.summary) {
        $hasSummaries = $false
    }
}

Write-Host ""
Write-Host "=== VALIDATION SUMMARY ===" -ForegroundColor Cyan
Write-Host ""

if ($allEnriched -and $hasEmbeddings -and $hasSummaries -and $docCount -gt 0) {
    Write-Host "  [PASS] Storage -> AI Search connectivity: Documents indexed successfully" -ForegroundColor Green
    Write-Host "  [PASS] AI Search -> AI Services (Text Analytics): KeyPhrases + Language detected" -ForegroundColor Green
    Write-Host "  [PASS] AI Search -> OpenAI (Embedding model): Vector embeddings generated" -ForegroundColor Green
    Write-Host "  [PASS] AI Search -> OpenAI (Chat completion): Text summaries generated" -ForegroundColor Green
    Write-Host "  [PASS] All $docCount documents fully enriched" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Network-secured AI Search pipeline with OpenAI model connectivity verified!" -ForegroundColor Green
} else {
    Write-Host "  Documents indexed: $docCount" -ForegroundColor DarkYellow
    if ($allEnriched) {
        Write-Host "  [PASS] Text Analytics skills (KeyPhrases + Language)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Text Analytics skills incomplete" -ForegroundColor DarkYellow
    }
    if ($hasEmbeddings) {
        Write-Host "  [PASS] Embedding model (text-embedding-3-small)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Embedding model did not produce vectors" -ForegroundColor DarkYellow
    }
    if ($hasSummaries) {
        Write-Host "  [PASS] Chat completion model (gpt-4.1) summaries" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Chat completion model did not produce summaries" -ForegroundColor DarkYellow
    }
    Write-Host ""
    Write-Host "  Check indexer warnings and AI Services connectivity." -ForegroundColor DarkYellow
}
