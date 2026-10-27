param([string]$Script = 'tools/phase6_acceptance/run_sandbox.py')
$ErrorActionPreference = 'Stop'
$workspace = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$config = Join-Path $PSScriptRoot 'acceptance.env'
$original = @{}
try {
    foreach ($line in Get-Content -LiteralPath $config) {
        if ($line -match '^([A-Z0-9_]+)=(.*)$') {
            $setting = $Matches[1]
            $original[$setting] = [Environment]::GetEnvironmentVariable($setting, 'Process')
            [Environment]::SetEnvironmentVariable($setting, $Matches[2], 'Process')
        }
    }
    Push-Location (Join-Path $workspace 'backend')
    try {
        & (Join-Path $workspace 'backend/.venv/Scripts/python.exe') (Join-Path $workspace $Script)
        if ($LASTEXITCODE -ne 0) { throw "Acceptance command exited $LASTEXITCODE" }
    } finally { Pop-Location }
} finally {
    foreach ($setting in $original.Keys) {
        [Environment]::SetEnvironmentVariable($setting, $original[$setting], 'Process')
    }
}
