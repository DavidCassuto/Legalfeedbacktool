# Feedback Tool Cleanup Script
# Snelle cleanup van alle Python processen en cache

param(
    [switch]$Force,
    [switch]$All
)

Write-Host "========================================" -ForegroundColor Red
Write-Host "Feedback Tool Cleanup Script" -ForegroundColor Red
Write-Host "========================================" -ForegroundColor Red

# Functie om alle Python processen te stoppen
function Stop-AllPythonProcesses {
    Write-Host "🛑 Stoppen van alle Python processen..." -ForegroundColor Red
    
    $processes = @()
    $processes += Get-Process python* -ErrorAction SilentlyContinue
    $processes += Get-Process python.exe -ErrorAction SilentlyContinue
    $processes += Get-Process pythonw* -ErrorAction SilentlyContinue
    
    if ($processes) {
        Write-Host "Gevonden processen:" -ForegroundColor Yellow
        foreach ($proc in $processes) {
            Write-Host "  - PID $($proc.Id): $($proc.ProcessName)" -ForegroundColor Gray
        }
        
        try {
            $processes | Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
            
            # Controleer of ze gestopt zijn
            $remaining = Get-Process python* -ErrorAction SilentlyContinue
            if ($remaining) {
                Write-Host "❌ Sommige processen weigeren te stoppen!" -ForegroundColor Red
                if ($Force) {
                    Write-Host "Force killing..." -ForegroundColor Red
                    $remaining | Stop-Process -Force -ErrorAction SilentlyContinue
                }
            } else {
                Write-Host "✅ Alle Python processen gestopt" -ForegroundColor Green
            }
        } catch {
            Write-Host "❌ Fout bij stoppen: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "✅ Geen Python processen gevonden" -ForegroundColor Green
    }
}

# Functie om cache op te schonen
function Clear-Cache {
    Write-Host "🧹 Opschonen cache..." -ForegroundColor Yellow
    
    $cacheItems = @(
        "src\__pycache__",
        "src\analysis\__pycache__",
        "__pycache__",
        "*.pyc",
        "*.pyo"
    )
    
    foreach ($item in $cacheItems) {
        if (Test-Path $item) {
            try {
                Remove-Item $item -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "  ✅ Opgeschoond: $item" -ForegroundColor Green
            } catch {
                Write-Host "  ⚠️  Kan niet opschonen: $item" -ForegroundColor Yellow
            }
        }
    }
}

# Functie om poorten vrij te maken
function Clear-Ports {
    Write-Host "🔌 Vrijmaken poorten..." -ForegroundColor Yellow
    
    $ports = @("5000", "8000", "8080")
    
    foreach ($port in $ports) {
        try {
            $netstat = netstat -ano | Select-String ":$port\s"
            if ($netstat) {
                Write-Host "  Poort $port is in gebruik:" -ForegroundColor Yellow
                foreach ($line in $netstat) {
                    $pid = ($line -split '\s+')[-1]
                    try {
                        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                        Write-Host "    - PID $pid ($($process.ProcessName))" -ForegroundColor Gray
                        if ($Force) {
                            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                            Write-Host "      ✅ Gestopt" -ForegroundColor Green
                        }
                    } catch {
                        Write-Host "    - PID $pid (onbekend proces)" -ForegroundColor Gray
                    }
                }
            } else {
                Write-Host "  ✅ Poort $port is vrij" -ForegroundColor Green
            }
        } catch {
            Write-Host "  ⚠️  Kan poort $port niet controleren" -ForegroundColor Yellow
        }
    }
}

# Hoofdscript
try {
    Write-Host "🚀 Start cleanup..." -ForegroundColor Cyan
    
    # Stop alle Python processen
    Stop-AllPythonProcesses
    
    # Maak poorten vrij
    Clear-Ports
    
    # Cleanup cache
    Clear-Cache
    
    if ($All) {
        Write-Host "🧹 Uitgebreide cleanup..." -ForegroundColor Cyan
        # Extra cleanup acties kunnen hier toegevoegd worden
    }
    
    Write-Host "`n✅ Cleanup voltooid!" -ForegroundColor Green
    Write-Host "💡 Start server met: .\start_server.ps1" -ForegroundColor Cyan
    
} catch {
    Write-Host "❌ Fout tijdens cleanup: $($_.Exception.Message)" -ForegroundColor Red
}

if (-not $Force) {
    Read-Host "Druk op Enter om af te sluiten"
} 