@echo off
echo ========================================
echo Legal Feedback Tool - Automatic Backup
echo ========================================
echo.

:: Set the project directory
set PROJECT_DIR=C:\ProjectFT
set BACKUP_SCRIPT=%PROJECT_DIR%\backup_script.py

:: Change to project directory
cd /d "%PROJECT_DIR%"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python and try again
    pause
    exit /b 1
)

:: Check if backup script exists
if not exist "%BACKUP_SCRIPT%" (
    echo ERROR: Backup script not found at %BACKUP_SCRIPT%
    pause
    exit /b 1
)

:: Create backups directory if it doesn't exist
if not exist "backups" mkdir backups

:: Run the backup script
echo Starting automatic backup...
echo Timestamp: %date% %time%
echo.

python "%BACKUP_SCRIPT%"

:: Check if backup was successful
if errorlevel 1 (
    echo.
    echo ERROR: Backup failed!
    pause
    exit /b 1
) else (
    echo.
    echo SUCCESS: Backup completed successfully!
    echo Backup location: %PROJECT_DIR%\backups\
)

echo.
echo Backup process finished at %time%
pause 