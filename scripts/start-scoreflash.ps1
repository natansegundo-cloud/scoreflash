$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$webRoot = Join-Path $projectRoot "web"
$environmentFile = Join-Path $projectRoot ".env"

function Wait-For-Key {
    Write-Host ""
    Read-Host "Aperte Enter para fechar esta janela"
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Ainda falta preparar o Python do ScoreFlash." -ForegroundColor Yellow
    Write-Host "Abra o README.md e siga a parte 'Usar é fácil'."
    Wait-For-Key
    exit 1
}

if (-not (Test-Path -LiteralPath $environmentFile)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $environmentFile
    Write-Host "Criei um arquivo .env opcional para futuras configurações." -ForegroundColor Green
}

if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules"))) {
    Write-Host "Preparando a tela do ScoreFlash pela primeira vez..." -ForegroundColor Cyan
    Push-Location $webRoot
    try {
        & npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw "O npm não conseguiu preparar a interface." }
    }
    finally {
        Pop-Location
    }
}

$listeningPorts = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in 8000, 5173 } |
    Select-Object -ExpandProperty LocalPort
if (8000 -in $listeningPorts -and 5173 -in $listeningPorts) {
    Write-Host "O ScoreFlash já parece estar ligado. Vou abrir a tela." -ForegroundColor Green
    Start-Process "http://127.0.0.1:5173"
    exit 0
}

Write-Host "Ligando o ScoreFlash..." -ForegroundColor Cyan
if (8000 -notin $listeningPorts) {
    Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "scoreflash.api:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $projectRoot -WindowStyle Hidden
}

if (5173 -notin $listeningPorts) {
    Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "5173") -WorkingDirectory $webRoot -WindowStyle Hidden
}

Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5173"
