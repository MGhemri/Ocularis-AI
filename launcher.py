"""
OCULARIS AI - LANCEUR MULTI-PROCESSUS
Version 1.1.0 - Détection automatique de l'environnement virtuel (.venv)
"""

import subprocess
import time
import webbrowser
import os
import sys
from pathlib import Path


def main():
    script_dir = Path(__file__).resolve().parent

    print("=" * 60)
    print("🚀 DÉMARRAGE DU SYSTÈME OCULARIS AI v1.1.0")
    print("   Audit Forensique Vidéo — Village Olympique (EGCSO)")
    print("=" * 60)

    # Détection automatique de l'environnement virtuel .venv
    venv_python_win = script_dir / ".venv" / "Scripts" / "python.exe"
    venv_python_posix = script_dir / ".venv" / "bin" / "python"

    if venv_python_win.exists():
        python_exec = str(venv_python_win)
        print(f"📦 Environnement virtuel actif : {python_exec}")
    elif venv_python_posix.exists():
        python_exec = str(venv_python_posix)
        print(f"📦 Environnement virtuel actif : {python_exec}")
    else:
        python_exec = sys.executable
        print(f"🐍 Python système utilisé : {python_exec}")

    # 1. Lancer le Moteur IA et l'Interface Web
    if os.name == 'nt':  # Windows
        p1 = subprocess.Popen([python_exec, "ai_engine.py"], cwd=str(script_dir), creationflags=subprocess.CREATE_NEW_CONSOLE)
        time.sleep(2)
        p2 = subprocess.Popen([python_exec, "web_interface.py"], cwd=str(script_dir), creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:  # Linux / macOS
        p1 = subprocess.Popen([python_exec, "ai_engine.py"], cwd=str(script_dir))
        time.sleep(2)
        p2 = subprocess.Popen([python_exec, "web_interface.py"], cwd=str(script_dir))

    print("✅ Moteur d'analyse IA et Serveur Web Flask lancés.")
    print("⏳ Ouverture automatique du Tableau de Bord dans 4 secondes...")
    time.sleep(4)

    # 2. Ouvrir le navigateur
    webbrowser.open("http://localhost:5000")

    print("\n--- SYSTÈME OPÉRATIONNEL ---")
    print("Tableau de bord : http://localhost:5000")
    print("Pour arrêter le système, fermez les consoles associées.")


if __name__ == "__main__":
    main()
