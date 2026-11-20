# 👁️ Ocularis AI — Forensic Video Analysis System

> **Version:** 1.1.0 (Stable / Enhanced Forensic)  
> **Statut:** Production / Grade Industriel  
> **Contexte:** Audit de sécurité & investigation forensique — Village Olympique (EGCSO Oran)  
> **Auteur :** Ghemri M (`contact@connect-gm.com` / `+213 549 777 366`)  

---

## 📋 Présentation

**Ocularis AI** est une solution d'analyse vidéo forensique automatisée conçue pour traiter de grands volumes d'archives de vidéosurveillance (CCTV).

Développé pour les audits de sécurité et les enquêtes sur les vols/incidents, ce système utilise la Vision par Ordinateur (**YOLOv8 + Multi-Object Tracking ByteTrack**) pour détecter, corréler, qualifier et documenter les anomalies dans des flux vidéo non structurés.

### 🚀 Fonctionnalités Clés (v1.1.0)
*   **Analyse Haute Performance Séquentielle :** Saut d'images ultra-rapide par `cap.grab()` (OpenCV) sans décompression inutile, 3x à 10x plus rapide sur les flux H.264/H.265 et conteneurs Dahua `.dav`.
*   **Multi-Object Tracking & Anti-Flooding :** Suivi par identifiant persistant (`track_id`) et temporisation intelligente (cooldown) pour éviter de générer des centaines de captures redondantes sur un sujet statique.
*   **Association Spatiale Personne ↔ Objet :** Détection de proximité/transport d'objets lourds ou de valeur (TV, Valises, Sacs à dos, PC portables) avec classification de sévérité automatique (**🔴 CRITIQUE**, **🟠 SUSPECT**, **🔵 VÉHICULE**).
*   **Workflow Forensique & Qualification :** Marquage direct par l'enquêteur (⭐ *Preuve Retenue*, 🗑️ *Faux Positif*, 📝 *Notes d'enquête*) persisté dans SQLite WAL.
*   **Rapports Officiels en 1 Clic :**
    *   **Rapport d'Investigation Imprimable / PDF (`/report`)** avec synthèse d'audit et emplacements signatures.
    *   **Export CSV Forensique (`/api/export/csv`)** avec empreintes d'intégrité SHA-256 des vidéos analysées.
*   **Exploration Récursive des Caméras :** Prise en charge des arborescences NVR multi-dossiers (`Cam_01/2026-11-20/...`).
*   **Alertes Telegram Optionnelles :** Notification instantanée avec photo vers le Bot Telegram de sécurité (`OCULARIS_TELEGRAM_ALERTS=1`).

---

## 🛠️ Architecture Technique

Le système est composé de deux modules autonomes communiquant via une base **SQLite en mode WAL (Write-Ahead Logging)** :

1.  **`ai_engine.py` (Moteur IA Backend) :** 
    *   Scanne récursivement le dossier `videos_source/`.
    *   Exécute l'inférence YOLOv8m avec accélération NVIDIA CUDA (ou CPU).
    *   Applique le suivi ByteTrack, l'association spatiale et l'anti-flooding.
    *   Enregistre les snapshots annotés dans `resultats_enquete/snapshots/`.
    *   Écrit dans `resultats_enquete/evidence_db.sqlite`.

2.  **`web_interface.py` (Dashboard Frontend Enquêteur) :**
    *   Serveur Flask optimisé.
    *   Interface web temps réel avec auto-refresh dynamique, filtres par caméra, sévérité, objet et qualification.
    *   Module de qualification des preuves et export de rapports.

---

## ⚙️ Installation & Démarrage

### Pré-requis
*   **OS :** Windows 10/11 (Recommandé) ou Linux / macOS.
*   **Python :** Version 3.10 ou supérieure (avec environnement virtuel recommandé).
*   **GPU :** Carte NVIDIA GeForce RTX (ex. RTX 3050 Ti) avec drivers CUDA pour une inférence maximale.

### Déploiement

1.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Déposer vos vidéos :**
    Déposez vos fichiers `.mp4`, `.avi`, `.mkv` ou `.dav` dans `videos_source/` (les sous-dossiers par caméra sont supportés).

3.  **Lancer le système :**
    *   **Sous Windows :** Double-cliquez sur `START_SYSTEM.bat`.
    *   **Ou en ligne de commande :**
        ```bash
        python launcher.py
        ```
    *   Accédez ensuite au tableau de bord sur **`http://localhost:5000`**.

---

## 🔧 Variables d'Environnement & Configuration

Les variables suivantes peuvent être configurées ou définies dans un fichier d'environnement :

| Variable | Description | Valeur par défaut |
| :--- | :--- | :--- |
| `OCULARIS_MODEL_SIZE` | Poids YOLO (`yolov8n.pt`, `yolov8m.pt`, `yolov8x.pt`) | `yolov8m.pt` |
| `OCULARIS_FRAME_SKIP` | Nombre de frames sautées entre 2 analyses | `10` |
| `OCULARIS_CONF_THRESHOLD` | Seuil de confiance minimal (0.0 à 1.0) | `0.40` |
| `OCULARIS_MIN_OBJ_RATIO` | Ratio de surface minimale pour objets suspects | `0.005` (0.5% écran) |
| `OCULARIS_PROXIMITY_PX` | Distance max d'association Personne ↔ Objet | `220 px` |
| `OCULARIS_COOLDOWN_SEC` | Délai anti-flooding entre 2 alertes identiques | `3.5 s` |
| `OCULARIS_TELEGRAM_ALERTS` | Activer les alertes Telegram (`1` ou `0`) | `0` |

---

## 📂 Structure du Répertoire

```text
OCULARIS-AI/
├── ai_engine.py          # Moteur d'analyse forensique YOLOv8 + Tracking (Backend)
├── web_interface.py      # Dashboard Enquêteur Flask + Qualification + Rapports (Frontend)
├── launcher.py           # Lanceur multi-processus Python avec détection .venv
├── START_SYSTEM.bat      # Lanceur rapide Windows
├── requirements.txt      # Dépendances Python allégées
├── yolov8m.pt            # Modèle YOLOv8 Medium pré-embarqué (52 Mo)
├── README.md             # Documentation officielle
├── LICENSE               # Licence MIT
│
├── videos_source/        # [ENTRÉE] Dossier de vos vidéos et flux NVR
│   ├── cam_entree.mp4
│   └── Cam_02/archive.dav
│
└── resultats_enquete/    # [SORTIE AUTOMATIQUE]
    ├── evidence_db.sqlite    # Base de données forensique SQLite WAL
    └── snapshots/            # Captures annotées (v{id}_f{frame}.jpg)
```

---

## 📞 Support & Contacts Officiels

*   **Auteur & Responsable Système :** Ghemri M (`GHEMRI M`)
*   **Organisation :** Complexe Olympique d'Oran (EGCSO)
*   **Email :** `contact@connect-gm.com`
*   **Téléphone :** `+213 549 777 366`
*   **Dépôt GitHub :** [https://github.com/MGhemri](https://github.com/MGhemri)

**Copyright © 2026 Ghemri M — Tous droits réservés.**
