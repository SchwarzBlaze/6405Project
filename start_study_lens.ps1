param(
    [string]$ServerUrl = "http://127.0.0.1:8080",
    [string]$ModelRef = "ggml-org/gemma-4-E2B-it-GGUF",
    [int]$StartupTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverDir = Join-Path $root "llama_cuda"
$serverExe = Join-Path $serverDir "llama-server.exe"
$mainScript = Join-Path $root "main.py"
$pythonGui = Join-Path $root ".venv\\Scripts\\pythonw.exe"
$pythonCli = Join-Path $root ".venv\\Scripts\\python.exe"
$healthUrl = "{0}/health" -f $ServerUrl.TrimEnd("/")

function Test-ServiceHealthy {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 300
    } catch {
        return $false
    }
}

if (-not (Test-Path $serverExe)) {
    throw "CUDA llama-server was not found: $serverExe"
}

if (-not (Test-Path $mainScript)) {
    throw "Main entry script was not found: $mainScript"
}

$pythonExe = $pythonGui
if (-not (Test-Path $pythonExe)) {
    $pythonExe = $pythonCli
}
if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment was not found. Please create .venv first."
}

if (-not (Test-ServiceHealthy -Url $healthUrl)) {
    $serverArgs = @(
        "-hf",
        $ModelRef,
        "--reasoning",
        "off",
        "-ngl",
        "all",
        "-c",
        "8192",
        "-np",
        "1",
        "-fa",
        "on"
    )

    Start-Process -FilePath $serverExe -ArgumentList $serverArgs -WorkingDirectory $serverDir

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $isHealthy = $false
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
        if (Test-ServiceHealthy -Url $healthUrl) {
            $isHealthy = $true
            break
        }
    }

    if (-not $isHealthy) {
        throw "Local AI service startup timed out. Please check the llama_cuda folder or run llama-server manually."
    }
}

Start-Process -FilePath $pythonExe -ArgumentList @($mainScript) -WorkingDirectory $root
