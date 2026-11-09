param(
    [int]$Port = 7910,
    [switch]$Stop,
    [switch]$Restart
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputDir = Join-Path $repoRoot 'outputs\danmaku-tts'
$pidFile = Join-Path $outputDir 'server.pid'
$healthUrl = "http://127.0.0.1:$Port/health"
$pm2Name = 'danmaku-tts'
$ecosystem = Join-Path $repoRoot 'ecosystem.danmaku-tts.config.cjs'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

if (-not (Get-Command pm2 -ErrorAction SilentlyContinue)) {
    throw 'PM2 is required: npm install -g pm2'
}

function Get-Pm2Process {
    $null = & pm2 describe $pm2Name 2>$null
    return $LASTEXITCODE -eq 0
}

if ($Stop) {
    if (Get-Pm2Process) {
        & pm2 stop $pm2Name --silent
        if ($LASTEXITCODE -ne 0) {
            throw "PM2 failed to stop $pm2Name."
        }
        Write-Output 'Danmaku TTS stopped.'
    } else {
        Write-Output 'Danmaku TTS is not managed by PM2.'
    }
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force
    }
    exit 0
}

$pm2Exists = Get-Pm2Process
if (-not $Restart -and $pm2Exists) {
    try {
        $existing = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($existing.status -eq 'ready') {
            Write-Output "Danmaku TTS is already running under PM2: http://127.0.0.1:$Port/tts"
            exit 0
        }
    } catch {}
}

$configPath = Join-Path $repoRoot 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Workflow config not found: $configPath"
}
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$runtime = [string]$config.rvc.runtime_python
if (-not (Test-Path -LiteralPath $runtime)) {
    throw "RVC runtime not found: $runtime"
}

$env:DANMAKU_TTS_PORT = [string]$Port
if ($pm2Exists) {
    & pm2 restart $pm2Name --update-env
} else {
    & pm2 start $ecosystem --only $pm2Name --update-env
}
if ($LASTEXITCODE -ne 0) {
    throw "PM2 failed to launch $pm2Name."
}
$null = & pm2 save

$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($health.status -eq 'ready') {
            Write-Output "Danmaku TTS ready under PM2: http://127.0.0.1:$Port/tts"
            exit 0
        }
    } catch {}
}

throw "Danmaku TTS did not become ready. Check: pm2 logs $pm2Name"
