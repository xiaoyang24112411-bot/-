$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env.prod"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Environment file not found: $envPath"
}

$secureKey = Read-Host "Paste your DeepSeek API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

try {
    $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw "API key cannot be empty."
    }

    $currentContent = Get-Content -LiteralPath $envPath
    $filteredContent = $currentContent | Where-Object {
        $_ -notmatch '^DEEPSEEK_(API_KEY|MODEL|BASE_URL)='
    }

    $newContent = @($filteredContent) + @(
        "DEEPSEEK_API_KEY=$plainKey",
        "DEEPSEEK_MODEL=deepseek-v4-flash",
        "DEEPSEEK_BASE_URL=https://api.deepseek.com"
    )

    Set-Content -LiteralPath $envPath -Value $newContent -Encoding UTF8
    Write-Host "DeepSeek configuration saved to .env.prod."
}
finally {
    if ($keyPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
    $plainKey = $null
    $secureKey = $null
}
