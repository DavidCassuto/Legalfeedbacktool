# Installeert een dagelijkse automatische backup van de DocuCheck database naar OneDrive
# Eenmalig uitvoeren als beheerder: .\installeer_dagelijkse_backup.ps1

$TaakNaam    = "DocuCheck_Database_Backup"
$Python      = "C:\Users\Davidcassuto\ProjectFT\venv_lokaal\Scripts\python.exe"
$Script      = "C:\Users\Davidcassuto\ProjectFT\backup_database.py"
$TijdstipUur = 9   # Elke ochtend om 09:00

# Verwijder bestaande taak als die er al is
Unregister-ScheduledTask -TaskName $TaakNaam -Confirm:$false -ErrorAction SilentlyContinue

$Actie     = New-ScheduledTaskAction -Execute $Python -Argument $Script -WorkingDirectory "C:\Users\Davidcassuto\ProjectFT"
$Trigger   = New-ScheduledTaskTrigger -Daily -At "${TijdstipUur}:00"
$Instellingen = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaakNaam `
    -Action $Actie `
    -Trigger $Trigger `
    -Settings $Instellingen `
    -Description "Dagelijkse backup van DocuCheck database naar OneDrive" `
    -RunLevel Highest

Write-Host ""
Write-Host "Dagelijkse backup ingesteld op elke ochtend om ${TijdstipUur}:00" -ForegroundColor Green
Write-Host "Backups worden opgeslagen in:" -ForegroundColor Cyan
Write-Host "  - OneDrive:     $env:USERPROFILE\OneDrive\DocuCheck_Backups\" -ForegroundColor Cyan
Write-Host "  - Google Drive: G:\My Drive\DocuCheck_Backups\" -ForegroundColor Cyan
Write-Host ""
Write-Host "Direct testen:" -ForegroundColor Yellow
Write-Host "  python backup_database.py" -ForegroundColor White
Write-Host "Backups bekijken:" -ForegroundColor Yellow
Write-Host "  python backup_database.py --list" -ForegroundColor White
