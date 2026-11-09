param(
    [int]$Port = 7910,
    [int]$IdleUnloadSeconds = 300,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Warm,
    [switch]$Silent
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$outputDir = Join-Path $repoRoot 'outputs\danmaku-tts'
$configPath = Join-Path $repoRoot 'config.json'

if ($Silent) {
    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    $runtime = [string]$config.rvc.runtime_python
    $pythonw = Join-Path (Split-Path -Parent $runtime) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw)) {
        $pythonw = $runtime
    }
    $launcher = Join-Path $PSScriptRoot 'danmaku_tts_launcher.py'
    $action = if ($Stop) { 'stop' } elseif ($Restart) { 'restart' } elseif ($Warm) { 'warm' } else { 'start' }
    & $pythonw $launcher --action $action --port $Port
    exit $LASTEXITCODE
}

$pidFile = Join-Path $outputDir 'server.pid'
$healthUrl = "http://127.0.0.1:$Port/health"
$warmUrl = "http://127.0.0.1:$Port/warm"
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
        if ($existing.status -in @('cold', 'loading', 'ready')) {
            if ($Warm) {
                $null = Invoke-RestMethod -Uri $warmUrl -TimeoutSec 5
            }
            Write-Output "Danmaku TTS supervisor is already running under PM2: http://127.0.0.1:$Port/tts (model: $($existing.status))"
            exit 0
        }
    } catch {}
}

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Workflow config not found: $configPath"
}
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$runtime = [string]$config.rvc.runtime_python
if (-not (Test-Path -LiteralPath $runtime)) {
    throw "RVC runtime not found: $runtime"
}

$env:DANMAKU_TTS_PORT = [string]$Port
$env:DANMAKU_TTS_IDLE_UNLOAD_SECONDS = [string]$IdleUnloadSeconds
if ($pm2Exists) {
    & pm2 delete $pm2Name --silent
    if ($LASTEXITCODE -ne 0) {
        throw "PM2 failed to remove the previous $pm2Name process."
    }
}
& pm2 start $ecosystem --only $pm2Name --update-env
if ($LASTEXITCODE -ne 0) {
    throw "PM2 failed to launch $pm2Name."
}
$null = & pm2 save

if ($Warm) {
    try {
        $null = Invoke-RestMethod -Uri $warmUrl -TimeoutSec 5
    } catch {
        throw "Danmaku TTS supervisor started, but warm-up could not be requested: $($_.Exception.Message)"
    }
}

$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($health.status -eq 'cold') {
            Write-Output "Danmaku TTS supervisor ready under PM2; model is cold: http://127.0.0.1:$Port/tts"
            exit 0
        }
        if ($health.status -eq 'ready') {
            Write-Output "Danmaku TTS warm and ready under PM2: http://127.0.0.1:$Port/tts"
            exit 0
        }
    } catch {}
}

throw "Danmaku TTS supervisor did not become ready. Check: pm2 logs $pm2Name"
