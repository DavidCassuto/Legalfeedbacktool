# Feedback Tool Server Manager - Eenvoudige Versie
# Gebruik dit script voor optimale werkwijze

param(
    [switch]$Debug
)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Feedback Tool Server Manager - Eenvoudig" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Controleer of we in de juiste venv zitten
$currentPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($currentPython -like "*venv_lokaal*") {
    Write-Host "✅ Al in venv_lokaal!" -ForegroundColor Green
    Write-Host "Python pad: $currentPython" -ForegroundColor Gray
} else {
    Write-Host "❌ Niet in venv_lokaal!" -ForegroundColor Red
    Write-Host "Activeer eerst de virtuele omgeving:" -ForegroundColor Yellow
    Write-Host "  .\venv_lokaal\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "Of gebruik: .\activate_venv.ps1" -ForegroundColor Cyan
    Write-Host "" -ForegroundColor White
    Write-Host "Daarna kun je dit script opnieuw uitvoeren." -ForegroundColor White
    exit 1
}

# Stop eventuele bestaande Python processen
Write-Host "Stoppen van bestaande Python processen..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python.exe -ErrorAction SilentlyContinue | Stop-Process -Force

# Start de server
Write-Host "Starten van de server..." -ForegroundColor Green

if ($Debug) {
    Write-Host "Debug mode: Gebruik main.py" -ForegroundColor Cyan
    python src\main.py
} else {
    Write-Host "Productie mode: Gebruik app.py" -ForegroundColor Cyan
    python src\app.py
}

Write-Host "`nServer gestopt." -ForegroundColor Cyan 