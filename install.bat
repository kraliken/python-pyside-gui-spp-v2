@echo off
setlocal

echo [INFO] Virtualis kornyezet aktivalasa...

REM Ellenorizzuk, hogy letezik-e a .venv
if not exist "%~dp0.venv\Scripts\activate.bat" (
    echo [HIBA] A .venv\Scripts\activate.bat nem talalhato!
    echo Elobb hozd letre a virtualis kornyezetet ebben a mappaban.
    pause
    exit /b 1
)

call "%~dp0.venv\Scripts\activate.bat"

echo [INFO] pip telepitese / frissitese a virtualis kornyezetben...

REM pip letrehozasa a venv-ben
python -m ensurepip --upgrade
if errorlevel 1 (
    echo [HIBA] Nem sikerult a pip-et letrehozni (ensurepip hiba).
    echo Ellenorizd, hogy a Python telepitese teljes (python.org rol) es nem hianyzik az ensurepip modul.
    goto end
)

REM pip frissitese
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [HIBA] Nem sikerult a pip frissitese.
    goto end
)

REM requirements.txt ellenorzese
if not exist "%~dp0requirements.txt" (
    echo [HIBA] A requirements.txt nem talalhato a projekt gyokermappajaban!
    goto end
)

echo [INFO] Csomagok telepitese a requirements.txt alapjan...
python -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo [HIBA] A telepites soran hiba tortent.
) else (
    echo [INFO] A csomagok sikeresen telepultek a virtualis kornyezetbe.
)

:end
echo.
echo Nyomj meg egy gombot a kilepeshez.
pause
