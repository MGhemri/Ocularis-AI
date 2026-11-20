# 👁️ Ocularis AI — Forensic Video Analysis & Real-Time RTSP Surveillance

> **Version:** 1.2.0 (Stable / RTSP & Live IP Camera Support)  
> **Statut:** Production / Grade Industriel  
> **Contexte:** Système Universel d'Analyse Vidéo Forensique & Surveillance Temps Réel CCTV  
> **Auteur :** Ghemri M (`contact@connect-gm.com` / `+213 549 777 366`)  

---

## 📋 Présentation

**Ocularis AI** est une solution complète de vision par ordinateur pour la vidéosurveillance (**CCTV**), combinant **analyse forensique d'archives volumineuses** et **surveillance temps réel de flux RTSP / caméras IP en direct**.

Développé pour les audits de sécurité, les centres de contrôle et les enquêtes sur les incidents, le système utilise **YOLOv8 + Multi-Object Tracking ByteTrack** pour identifier, suivre, qualifier et documenter les anomalies sans aucune latence d'accumulation.

---

## 🚀 Fonctionnalités Clés (v1.2.0)

### 📹 1. Surveillance Temps Réel Multi-Caméras (RTSP & Caméras IP)
*   **Ingestion Bufferless Zéro-Latence :** Threading dédié avec capture continue sans buffer OpenCV (`CAP_PROP_BUFFERSIZE=1`), éliminant tout décalage temporel avec la réalité.
*   **Auto-Reconnexion Continue :** Détection automatique des coupures réseau ou redémarrages de caméra avec boucle de reprise intelligente et transport forcé sur TCP (`rtsp_transport;tcp`).
*   **Mur de Surveillance Web (Live MJPEG) :** Diffusion en direct des caméras dans le navigateur (`/api/stream/<camera_id>`) avec affichage commutable des **bounding boxes IA** (Mode IA vs Mode Brut).
*   **Outil de Test de Connexion Intégré :** Validation immédiate des identifiants et URLs RTSP (`/api/cameras/test`) avec rapport de résolution et FPS sans recharger la page.
*   **Presets Constructeurs Intégrés :** Préréglages immédiats pour **Dahua, Hikvision, Uniview, Axis et webcams USB locales (`0`)**.

### 🔍 2. Analyse Forensique d'Archives Vidéo
*   **Analyse Haute Performance Séquentielle :** Saut d'images rapide par `cap.grab()` (OpenCV) sans décompression inutile, 3x à 10x plus rapide sur flux H.264/H.265 et conteneurs Dahua `.dav`.
*   **Multi-Object Tracking & Anti-Flooding :** Suivi par identifiant persistant (`track_id`) et temporisation intelligente (`COOLDOWN_SECONDS = 3.5s`) pour éviter la saturation de captures sur des sujets immobiles.
*   **Association Spatiale Personne ↔ Objet :** Détection de transport d'objets lourds ou de valeur (TV, Valises, Sacs à dos, PC portables) avec classification automatique de sévérité (**🔴 CRITIQUE**, **🟠 SUSPECT**, **🔵 VÉHICULE**).
*   **Exploration Récursive des Sous-Dossiers NVR :** Prise en charge des arborescences de caméras (`Cam_01/2026-11-20/...`).

### ⚖️ 3. Workflow Forensique & Rapports Officiels
*   **Qualification Directe par l'Enquêteur :** Marquage en 1 clic (⭐ *Preuve Retenue*, 🗑️ *Faux Positif*, 📝 *Notes d'enquête*) persisté dans SQLite WAL.
*   **Rapport d'Investigation Imprimable / PDF (`/report`)** avec synthèse d'audit et emplacements signatures.
*   **Export CSV Forensique (`/api/export/csv`)** avec empreintes d'intégrité SHA-256 pour les archives et label `FLUX_DIRECT_RTSP` pour les caméras en direct.
*   **Alertes Telegram Instantanées :** Notification instantanée avec photo vers votre Bot Telegram de sécurité (`OCULARIS_TELEGRAM_ALERTS=1`).

---

## 🛠️ Architecture Technique

```text
OCULARIS-AI/
├── rtsp_manager.py       # Gestionnaire centralisé des flux RTSP & inférence temps réel (Bufferless)
├── ai_engine.py          # Moteur d'analyse forensique YOLOv8 + ByteTrack (Batch & CLI Live)
├── web_interface.py      # Serveur Flask, Dashboard Enquêteur, Mur RTSP & Streaming MJPEG
├── launcher.py           # Lanceur multi-processus Python avec détection automatique de .venv
├── START_SYSTEM.bat      # Lanceur rapide Windows (.venv\Scripts\python.exe)
├── cameras.json          # Fichier de configuration des caméras IP (persistance JSON)
├── requirements.txt      # Dépendances Python (ultralytics, opencv-python, flask, tqdm)
├── yolov8m.pt            # Poids YOLOv8 Medium pré-embarqués (52 Mo)
├── README.md             # Documentation officielle Ocularis AI
├── LICENSE               # Licence MIT Copyright (c) 2026 Ghemri M
│
├── videos_source/        # [ENTRÉE] Dossier de vos vidéos d'archives et conteneurs NVR
└── resultats_enquete/    # [SORTIE AUTOMATIQUE]
    ├── evidence_db.sqlite    # Base forensique SQLite WAL (tables videos & events)
    └── snapshots/            # Captures annotées (v{id}_f{frame}.jpg & live_{cam}_{ts}.jpg)
```

---

## ⚙️ Configuration des Caméras IP (`cameras.json`)

Le fichier `cameras.json` est géré automatiquement via l'interface web (Onglet **Configuration Caméras IP**), mais peut aussi être édité manuellement :

```json
[
  {
    "id": "cam_01",
    "name": "Caméra 01 - Entrée Principale",
    "url": "rtsp://admin:motdepasse@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0",
    "enabled": true,
    "fps_analyze": 2.0,
    "cooldown_sec": 3.5
  },
  {
    "id": "cam_02",
    "name": "Caméra 02 - Parking & Accès Véhicules",
    "url": "rtsp://admin:motdepasse@192.168.1.101:554/h264Preview_01_main",
    "enabled": true,
    "fps_analyze": 2.0,
    "cooldown_sec": 3.5
  }
]
```

### URLs types selon les constructeurs de caméras :
*   **Dahua :** `rtsp://admin:pass@IP:554/cam/realmonitor?channel=1&subtype=0`
*   **Hikvision :** `rtsp://admin:pass@IP:554/Streaming/Channels/101`
*   **Uniview :** `rtsp://admin:pass@IP:554/unicast/c1/s0/live`
*   **Axis :** `rtsp://root:pass@IP:554/axis-media/media.amp`
*   **Webcam USB locale :** `0` ou `1`

---

## 🚀 Démarrage Rapide

1.  **Démarrage du système complet :**
    *   **Sous Windows :** Double-cliquez sur `START_SYSTEM.bat`.
    *   **Ou en ligne de commande :**
        ```bash
        python launcher.py
        ```
    *   Accédez ensuite à l'interface sur **`http://localhost:5000`**.

2.  **Surveillance RTSP seule en mode console (Headless) :**
    ```bash
    python ai_engine.py --live
    ```

3.  **Analyse par lot d'archives vidéo :**
    Déposez vos fichiers `.mp4`, `.avi`, `.mkv` ou `.dav` dans `videos_source/`, puis exécutez :
    ```bash
    python ai_engine.py --batch
    ```

---

## 🔧 Variables d'Environnement

| Variable | Description | Valeur par défaut |
| :--- | :--- | :--- |
| `OCULARIS_CAMERAS_CONFIG` | Chemin vers le fichier des caméras | `./cameras.json` |
| `OCULARIS_MODEL_SIZE` | Fichier de poids YOLOv8 | `yolov8m.pt` |
| `OCULARIS_FRAME_SKIP` | Nombre d'images sautées (mode batch) | `10` |
| `OCULARIS_CONF_THRESHOLD` | Seuil de confiance minimal (0.0 à 1.0) | `0.40` |
| `OCULARIS_COOLDOWN_SEC` | Délai anti-flooding entre alertes identiques | `3.5 s` |
| `OCULARIS_PROXIMITY_PX` | Distance d'association Personne ↔ Objet | `220 px` |
| `OCULARIS_TELEGRAM_ALERTS` | Activer les alertes photo Telegram | `0` |

---

## 📞 Support & Contacts Officiels

*   **Auteur & Responsable Système :** Ghemri M (`GHEMRI M`)
*   **Email :** `contact@connect-gm.com`
*   **Téléphone :** `+213 549 777 366`
*   **Dépôt GitHub :** [https://github.com/MGhemri/Ocularis-AI](https://github.com/MGhemri/Ocularis-AI)

**Copyright © 2026 Ghemri M — Licence MIT — Tous droits réservés.**
