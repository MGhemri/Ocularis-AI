@echo off
title LANCEUR OCULARIS AI
color 0A
echo ========================================================
echo   DEMARRAGE DU SYSTEME OCULARIS AI (V1.3.0)
echo   Systeme Universel d'Analyse Forensique & RTSP Live
echo ========================================================

set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo [OK] Environnement virtuel .venv detecte.
) else (
    echo [INFO] Python systeme utilise.
)

:: 1. Lancer le Moteur IA dans une nouvelle fenetre
echo Lancement du Moteur d'Analyse Forensique...
start "OCULARIS AI - MOTEUR IA (Ne pas fermer)" cmd /k "cd /d "%~dp0" && "%PYTHON_EXE%" ai_engine.py"

:: Petite pause de 2 secondes pour laisser le moteur s'initialiser
timeout /t 2 >nul

:: 2. Lancer l'Interface Web dans une nouvelle fenetre
echo Lancement du Serveur Web Forensique...
start "OCULARIS AI - SERVEUR WEB (Ne pas fermer)" cmd /k "cd /d "%~dp0" && "%PYTHON_EXE%" web_interface.py"

:: Petite pause de 4 secondes pour laisser Flask demarrer
timeout /t 4 >nul

:: 3. Ouvrir le navigateur automatiquement
echo Ouverture du Tableau de Bord...
start http://localhost:5000

echo.
echo ========================================================
echo   TOUT EST LANCE !
echo   Tableau de bord : http://localhost:5000
echo   Rapport PDF     : http://localhost:5000/report
echo   Ne fermez pas les deux autres fenetres noires.
echo ========================================================
echo.
pause
