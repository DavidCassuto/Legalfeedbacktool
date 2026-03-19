# Feedback Tool Server Manager - Robuuste Versie
# Automatische cleanup en server management met venv activatie

param(
    [switch]$Force,
    [switch]$Debug,
    [switch]$Clean
)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Feedback Tool Server Manager v2.1" -ForegroundColor Cyan
Write-Host "Automatische venv activatie & cleanup" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Functie om virtuele omgeving te activeren
function Activate-VirtualEnvironment {
    Write-Host "Activeren van virtuele omgeving..." -ForegroundColor Yellow
    
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
    
    # Controleer of we al in de juiste venv zitten
    $currentPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($currentPython -like "*venv_lokaal*") {
        Write-Host "✅ Al in venv_lokaal!" -ForegroundColor Green
        Write-Host "Python pad: $currentPython" -ForegroundColor Gray
        return
    }
    
    Write-Host "⚠️  Niet in venv_lokaal. Handmatige activatie vereist." -ForegroundColor Yellow
    Write-Host "Voer uit: .\venv_lokaal\Scripts\Activate.ps1" -ForegroundColor Cyan
    Write-Host "Of gebruik: .\activate_venv.ps1" -ForegroundColor Cyan
    exit 1
}

# Functie om processen te vinden en stoppen
function Stop-AllPythonProcesses {
    Write-Host "Zoeken naar Python processen..." -ForegroundColor Yellow
    
    # Zoek alle Python processen (inclusief subprocessen)
    $pythonProcesses = @()
    $pythonProcesses += Get-Process python -ErrorAction SilentlyContinue
    $pythonProcesses += Get-Process python.exe -ErrorAction SilentlyContinue
    $pythonProcesses += Get-Process pythonw -ErrorAction SilentlyContinue
    $pythonProcesses += Get-Process pythonw.exe -ErrorAction SilentlyContinue
    
    if ($pythonProcesses) {
        Write-Host "Gevonden Python processen: $($pythonProcesses.Count)" -ForegroundColor Yellow
        foreach ($process in $pythonProcesses) {
            Write-Host "  - PID $($process.Id): $($process.ProcessName)" -ForegroundColor Gray
        }
        
        # Stop alle processen
        try {
            $pythonProcesses | Stop-Process -Force
            Write-Host "Alle Python processen gestopt!" -ForegroundColor Green
        }
        catch {
            Write-Host "Waarschuwing: Kon niet alle processen stoppen: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Geen Python processen gevonden." -ForegroundColor Green
    }
}

# Functie om poort te controleren
function Test-Port {
    param([int]$Port)
    
    try {
        $connection = Test-NetConnection -ComputerName localhost -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        return $connection
    }
    catch {
        return $false
    }
}

# Functie om cache op te schonen
function Clear-Cache {
    Write-Host "Opschonen van cache..." -ForegroundColor Yellow
    
    # Verwijder Python cache bestanden
    $cachePaths = @(
        "__pycache__",
        "src\__pycache__",
        "src\analysis\__pycache__",
        "*.pyc",
        "*.pyo"
    )
    
    foreach ($path in $cachePaths) {
        if (Test-Path $path) {
            try {
                Remove-Item $path -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  - Cache opgeschoond: $path" -ForegroundColor Gray
            }
            catch {
                Write-Host "  - Kon cache niet opschonen: $path" -ForegroundColor Yellow
            }
        }
    }
    
    Write-Host "Cache opschoning voltooid!" -ForegroundColor Green
}

# Hoofdscript
try {
    # 1. Stop alle Python processen
    Stop-AllPythonProcesses
    
    # 2. Controleer poort 5000
    if (Test-Port -Port 5000) {
        Write-Host "Waarschuwing: Poort 5000 is nog in gebruik!" -ForegroundColor Yellow
        if (-not $Force) {
            Write-Host "Gebruik -Force om door te gaan..." -ForegroundColor Yellow
            exit 1
        }
    }
    
    # 3. Cache opschonen als gevraagd
    if ($Clean) {
        Clear-Cache
    }
    
    # 4. Activeer virtuele omgeving
    Activate-VirtualEnvironment

    # 4b. Laad API keys uit .env bestand
    $envFile = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^\s*([^#][^=]+)=(.+)$") {
                [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
            }
        }
        Write-Host "API keys geladen uit .env" -ForegroundColor Green
    } else {
        Write-Host "LET OP: Geen .env bestand gevonden. Maak .env aan met je API keys." -ForegroundColor Yellow
    }
    # 5. Start de server
    Write-Host "Starten van de server..." -ForegroundColor Green
    
    # Gebruik expliciet de venv python
    $venvPython = "venv_lokaal\Scripts\python.exe"
    
    if ($Debug) {
        Write-Host "Debug mode: Gebruik main.py" -ForegroundColor Cyan
        & $venvPython src\main.py
    } else {
        Write-Host "Productie mode: Gebruik app.py" -ForegroundColor Cyan
        & $venvPython src\app.py
    }
}
catch {
    Write-Host "Kritieke fout: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Probeer: .\start_server.ps1 -Force" -ForegroundColor Yellow
    exit 1
}

# Cleanup bij afsluiten
Write-Host "`nServer gestopt. Voor herstart: .\start_server.ps1" -ForegroundColor Cyan 