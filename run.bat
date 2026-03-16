@echo off
echo [INFO] Virtualis kornyezet aktivalasa...
if not exist "%~dp0.venv\Scripts\activate.bat" (
    echo [HIBA] A venv nem talalhato! Kerlek, masold be a venv mappat a projektbe.
    pause
    exit /b
)
call "%~dp0.venv\Scripts\activate.bat"


echo [INFO] Alkalmazas inditasa...

python main.py

echo ---
echo A program bezarult. Nyomj meg egy gombot a kilepeshez.
pause
