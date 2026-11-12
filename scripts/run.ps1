$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "Virtual environment missing. Run scripts\setup.ps1 first."
    exit 1
}

if (Test-Path ".env") {
    foreach ($line in Get-Content ".env") {
        $trimmed = $line.Trim()
        if ($trimmed -and -not $trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
            $parts = $trimmed.Split("=", 2)
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }
}

if (-not $env:PORT) { $env:PORT = "8000" }
& ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port $env:PORT
