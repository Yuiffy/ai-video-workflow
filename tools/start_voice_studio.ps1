param([int]$Port = 7899)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioOutput = Join-Path $studioRoot 'outputs\voice-studio'
New-Item -ItemType Directory -Path $studioOutput -Force | Out-Null
try {
    $studioExisting = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/settings" -TimeoutSec 2
    if ($null -ne $studioExisting.provider) {
        Write-Output "Voice studio is already running: http://127.0.0.1:$Port/"
        exit 0
    }
} catch {}
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) {
    $studioPython = (Get-Command python -ErrorAction Stop).Source
}
Start-Process -FilePath $studioPython -ArgumentList @('-m', 'src.voice_studio', '--port', $Port) -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioOutput 'server.log') -RedirectStandardError (Join-Path $studioOutput 'server-error.log')
Write-Output "Voice studio starting: http://127.0.0.1:$Port/"
