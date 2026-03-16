@echo off
setlocal

echo [INFO] Projekt konyvtar beallitasa...
cd /d "%~dp0"

echo [INFO] Virtualis kornyezet aktivalasa...
if not exist ".venv\Scripts\activate.bat" (
    echo [HIBA] A .venv\Scripts\activate.bat nem talalhato!
    echo Elobb hozd letre a virtualis kornyezetet ebben a mappaban:
    echo   py -3 -m venv .venv
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo [INFO] pip letrehozasa / frissitese...
python -m ensurepip --upgrade
python -m pip install --upgrade pip

echo [INFO] requirements.txt telepitese (ha letezik)...
if exist "requirements.txt" (
    python -m pip install -r "requirements.txt"
) else (
    echo [FIGYELMEZTETES] Nincs requirements.txt a mappaban, ezt a lepest kihagyom.
)

echo [INFO] PySide6 telepitese / frissitese a virtualis kornyezetbe...
python -m pip install --upgrade PySide6

echo.
echo [INFO] Keszen vagyunk. Telepitett csomagok kozott a PySide6:
python -m pip show PySide6

echo.
echo Nyomj meg egy gombot a kilepeshez.
pause
