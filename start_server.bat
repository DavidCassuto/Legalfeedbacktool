@echo off
REM Feedback Tool Server Manager - Windows Batch Version
REM Automatische cleanup en server management

echo ========================================
echo Feedback Tool Server Manager v2.0
echo Windows Batch Version
echo ========================================

REM Check parameters
set FORCE_MODE=0
set DEBUG_MODE=0
set CLEAN_MODE=0

:parse_args
if "%1"=="-Force" set FORCE_MODE=1
if "%1"=="-Debug" set DEBUG_MODE=1
if "%1"=="-Clean" set CLEAN_MODE=1
if "%1"=="-Force" goto :next_arg
if "%1"=="-Debug" goto :next_arg
if "%1"=="-Clean" goto :next_arg
goto :start_cleanup

:next_arg
shift
goto :parse_args

:start_cleanup
echo.
echo [1/5] Zoeken naar Python processen...
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I "python.exe" >NUL
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Python processen gevonden!
    echo Stoppen van alle Python processen...
    taskkill /F /IM python.exe >NUL 2>&1
    timeout /t 3 /nobreak >NUL
)

echo [2/5] Controleren poort 5000...
netstat -ano | findstr ":5000" >NUL
if %ERRORLEVEL% EQU 0 (
    echo WARNING: Poort 5000 is in gebruik!
    echo Probeer processen op poort 5000 te stoppen...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000"') do (
        taskkill /F /PID %%a >NUL 2>&1
    )
    timeout /t 2 /nobreak >NUL
)

echo [3/5] Opschonen Python cache...
if exist "src\__pycache__" (
    rmdir /s /q "src\__pycache__" >NUL 2>&1
    echo   Opgeschoond: src\__pycache__
)
if exist "src\analysis\__pycache__" (
    rmdir /s /q "src\analysis\__pycache__" >NUL 2>&1
    echo   Opgeschoond: src\analysis\__pycache__
)
if exist "__pycache__" (
    rmdir /s /q "__pycache__" >NUL 2>&1
    echo   Opgeschoond: __pycache__
)

echo [4/5] Testen imports...
if %FORCE_MODE% EQU 0 (
    python -c "import sys; sys.path.insert(0, 'src'); from main import app; print('OK: main.py imports')" >NUL 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Import test gefaald!
        echo Gebruik -Force parameter om door te gaan
        pause
        exit /b 1
    )
)

echo [5/5] Starten server...
if exist "venv_lokaal\Scripts\activate.bat" (
    echo Activeren virtuele omgeving...
    call "venv_lokaal\Scripts\activate.bat"
)

if %DEBUG_MODE% EQU 1 (
    echo Debug mode: AAN
    python src\main.py
) else (
    echo Productie mode: AAN
    python src\app.py
)

echo.
echo Server gestopt. Voor herstart: start_server.bat
pause 