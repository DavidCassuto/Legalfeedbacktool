# Feedback Tool - Virtuele Omgeving Activatie
# Handmatige activatie van venv_lokaal

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Feedback Tool - Venv Activatie" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Check of venv_lokaal bestaat
if (-not (Test-Path "venv_lokaal")) {
    Write-Host "ERROR: Virtuele omgeving 'venv_lokaal' niet gevonden!" -ForegroundColor Red
    Write-Host "Maak eerst een virtuele omgeving aan:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv_lokaal" -ForegroundColor White
    Write-Host "  .\venv_lokaal\Scripts\Activate" -ForegroundColor White
    Write-Host "  pip install -r requirements.txt" -ForegroundColor White
    exit 1
}

# Check of activate script bestaat
$activateScript = "venv_lokaal\Scripts\Activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-Host "ERROR: Activate script niet gevonden in $activateScript" -ForegroundColor Red
    exit 1
}

# Activeer de virtuele omgeving
try {
    Write-Host "Activeren van venv_lokaal..." -ForegroundColor Yellow
    & $activateScript
    Write-Host "Virtuele omgeving geactiveerd!" -ForegroundColor Green
    Write-Host "Python pad: $(Get-Command python | Select-Object -ExpandProperty Source)" -ForegroundColor Gray
    Write-Host "Prompt zou nu moeten tonen: (venv_lokaal) PS C:\ProjectFT>" -ForegroundColor Cyan
}
catch {
    Write-Host "ERROR: Kon virtuele omgeving niet activeren: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} 