$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env.prod"
$validateUrl = "https://api.themoviedb.org/3/authentication"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Environment file not found: $envPath"
}

Write-Host "Paste the TMDB API Read Access Token (not the shorter v3 API key)."
$secureToken = Read-Host "TMDB API Read Access Token" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
$plainToken = $null

try {
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        throw "TMDB token cannot be empty."
    }

    try {
        $headers = @{ Authorization = "Bearer $plainToken" }
        $validation = Invoke-RestMethod `
            -Uri $validateUrl `
            -Method Get `
            -Headers $headers `
            -TimeoutSec 20
        if ($validation.success -ne $true) {
            throw "TMDB did not accept this token."
        }
    }
    catch {
        throw "TMDB token validation failed. Check that you copied the API Read Access Token."
    }

    $currentContent = Get-Content -LiteralPath $envPath
    $filteredContent = $currentContent | Where-Object {
        $_ -notmatch '^TMDB_(ACCESS_TOKEN|API_BASE_URL)='
    }
    $newContent = @($filteredContent) + @(
        "TMDB_ACCESS_TOKEN=$plainToken",
        "TMDB_API_BASE_URL=https://api.themoviedb.org/3"
    )

    Set-Content -LiteralPath $envPath -Value $newContent -Encoding UTF8
    Write-Host "TMDB configuration validated and saved to .env.prod."
    Write-Host "Return to Codex and reply: TMDB configured"
}
finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    $plainToken = $null
    $secureToken = $null
}
