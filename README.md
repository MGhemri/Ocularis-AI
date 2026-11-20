# Ocularis AI — Forensic Video Analysis & Real-Time RTSP Surveillance

> **Version :** 1.2.0 (Stable / RTSP & Live IP Camera Support)  
> **Statut :** Production / Grade Industriel  
> **Contexte :** Système Universel d'Analyse Vidéo Forensique & Surveillance Temps Réel CCTV  
> **Développeur :** Ghemri M (`contact@connect-gm.com` / `+213 549 777 366`)  

---

## 1. Presentation Generale

**Ocularis AI** est une solution logicielle de vision par ordinateur dediee a la videosurveillance (**CCTV**), combinant **l'analyse forensique d'archives volumineuses** et **la surveillance continue de flux RTSP / cameras IP en direct**.

Concu pour les audits de securite, les centres de controle et les enquetes sur incidents, le systeme exploite les modeles **YOLOv8** associes a l'algorithme de suivi multi-objets **ByteTrack** pour detecter, suivre, classifier et documenter les anomalies sans latence d'accumulation.

---

## 2. Fonctionnalites Principales (v1.2.0)

### 2.1. Surveillance Temps Reel Multi-Cameras (RTSP & IP)
*   **Ingestion Bufferless Zero-Latence :** Capture multi-threadee avec vidage de tampon OpenCV (`CAP_PROP_BUFFERSIZE = 1`), eliminant tout decalage temporel avec la realite.
*   **Auto-Reconnexion Reseau sur Transport TCP :** Forcage du transport TCP (`rtsp_transport;tcp`) pour neutraliser les corruptions de paquets UDP. Reconnexion continue et transparente en cas de coupure reseau ou reboot camera.
*   **Mur de Surveillance Web (Streaming MJPEG) :** Diffusion video en direct sur navigateur (`/api/stream/<camera_id>`) avec commutation instantanee entre Mode IA (bounding boxes, track IDs, scores) et Mode Brut.
*   **Outil de Diagnostic Reseau Integre :** Verification immediate de la connectivite RTSP (`/api/cameras/test`) avec restitution de la resolution, du debit d'images et du statut de reponse.
*   **Prereglages Constructeurs :** Profils preconfigures pour cameras Dahua, Hikvision, Uniview, Axis et webcams USB locales (`0`).

### 2.2. Analyse Forensique d'Archives Video
*   **Traitement Sequentiel Optimise :** Saut rapide d'images par `cap.grab()` (OpenCV) sans deballage lourd, augmentant le debit de traitement de 3x a 10x sur les codecs H.264/H.265 et conteneurs proprietaires Dahua `.dav`.
*   **Suivi Multi-Objets & Anti-Flooding :** Association d'identifiants persistants (`track_id`) et fenetre de temporisation parametrable (`COOLDOWN_SECONDS = 3.5s`) pour eviter la multiplication de captures redondantes sur des cibles statiques.
*   **Correlation Spatiale Personne / Objet :** Detection de manipulation et de transport d'objets lourds ou sensibles (valises, sacs, ecrans, ordinateurs portables) avec graduation de la severite (**CRITIQUE**, **SUSPECT**, **INFO**).
*   **Exploration Recursive des Repertoires NVR :** Prise en charge automatique des arborescences de stockage CCTV (`Cam_01/2026-11-20/...`).

### 2.3. Chaine de Traitement Forensique & Rapports
*   **Qualification Judiciaire des Preuves :** Marquage direct par l'analyste (*Preuve Retenue*, *Faux Positif*, *Notes d'enquete*) consigne dans la base SQLite WAL.
*   **Rapport d'Investigation Officiel (`/report`) :** Synthese d'audit imprimable et exportable en PDF avec metriques d'incidents et zones de visa d'autorite.
*   **Export Forensique CSV (`/api/export/csv`) :** Registre conforme RFC-4180 avec empreintes SHA-256 des fichiers sources et marqueur d'origine `FLUX_DIRECT_RTSP`.
*   **Passerelle d'Alerte Telegram :** Notification opt-in instantanee avec capture photo vers le bot securise (`OCULARIS_TELEGRAM_ALERTS=1`).

---

## 3. Architecture Technique

```text
OCULARIS-AI/
├── rtsp_manager.py       # Ingestion bufferless RTSP, auto-reconnexion TCP & streaming MJPEG
├── ai_engine.py          # Moteur forensique YOLOv8 + ByteTrack (Batch & CLI Live --live)
├── web_interface.py      # Serveur Flask, Mur de surveillance RTSP, Qualification & Rapports
├── launcher.py           # Lanceur multi-processus avec detection automatique .venv
├── START_SYSTEM.bat      # Lanceur rapide Windows (.venv\Scripts\python.exe)
├── cameras.json          # Registre de configuration des cameras IP (persistance JSON)
├── requirements.txt      # Dependances Python certifiees (ultralytics, opencv, flask, tqdm)
├── yolov8m.pt            # Poids YOLOv8 Medium pre-embarques (52,1 Mo)
├── tests/                # Suite de validation automatisee (test_rtsp_suite.py)
├── README.md             # Documentation officielle Ocularis AI
├── LICENSE               # Licence MIT Copyright (c) 2026 Ghemri M
│
├── videos_source/        # [ENTREE] Dossier des archives video et conteneurs NVR
└── resultats_enquete/    # [SORTIE]
    ├── evidence_db.sqlite    # Base forensique SQLite WAL (tables videos & events)
    └── snapshots/            # Captures annotees (v{id}_f{frame}.jpg & live_{cam}_{ts}.jpg)
```

---

## 4. Configuration des Cameras IP (`cameras.json`)

Le fichier `cameras.json` est maintenu automatiquement via l'interface web (Onglet **Configuration Cameras IP**), ou directement editable :

```json
[
  {
    "id": "cam_01",
    "name": "Camera 01 - Entree Principale",
    "url": "rtsp://admin:motdepasse@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0",
    "enabled": true,
    "fps_analyze": 2.0,
    "cooldown_sec": 3.5
  },
  {
    "id": "cam_02",
    "name": "Camera 02 - Parking & Acces Vehicules",
    "url": "rtsp://admin:motdepasse@192.168.1.101:554/h264Preview_01_main",
    "enabled": true,
    "fps_analyze": 2.0,
    "cooldown_sec": 3.5
  }
]
```

### Syntaxes d'URL RTSP courantes :
*   **Dahua :** `rtsp://admin:pass@IP:554/cam/realmonitor?channel=1&subtype=0`
*   **Hikvision :** `rtsp://admin:pass@IP:554/Streaming/Channels/101`
*   **Uniview :** `rtsp://admin:pass@IP:554/unicast/c1/s0/live`
*   **Axis :** `rtsp://root:pass@IP:554/axis-media/media.amp`
*   **Webcam USB locale :** `0` ou `1`

---

## 5. Instructions de Demarrage

### 5.1. Demarrage du Systeme Complet
*   **Sous Windows :** Executer `START_SYSTEM.bat`.
*   **En ligne de commande :**
    ```bash
    python launcher.py
    ```
*   Acceder a l'interface d'investigation sur **`http://localhost:5000`**.

### 5.2. Surveillance RTSP en Mode Console (Headless)
Pour executer uniquement la surveillance temps reel sur un serveur sans interface graphique :
```bash
python ai_engine.py --live
```

### 5.3. Analyse Forensique par Lot (Batch)
Deposer les fichiers video (`.mp4`, `.avi`, `.mkv`, `.dav`) dans `videos_source/`, puis executer :
```bash
python ai_engine.py --batch
```

---

## 6. Variables d'Environnement

| Variable | Description | Valeur par defaut |
| :--- | :--- | :--- |
| `OCULARIS_CAMERAS_CONFIG` | Chemin vers le fichier des cameras | `./cameras.json` |
| `OCULARIS_MODEL_SIZE` | Fichier de poids YOLOv8 | `yolov8m.pt` |
| `OCULARIS_FRAME_SKIP` | Pas d'echantillonnage d'images (mode batch) | `10` |
| `OCULARIS_CONF_THRESHOLD` | Seuil de confiance minimal (0.0 a 1.0) | `0.40` |
| `OCULARIS_COOLDOWN_SEC` | Delai anti-flooding entre alertes identiques | `3.5 s` |
| `OCULARIS_PROXIMITY_PX` | Rayon maximal de correlation Personne / Objet | `220 px` |
| `OCULARIS_TELEGRAM_ALERTS` | Activation des alertes photo Telegram (`1` / `0`) | `0` |

---

## 7. Contacts & Mention Legale

*   **Développeur :** Ghemri M (`GHEMRI M`)
*   **Courriel Professionnel :** `contact@connect-gm.com`
*   **Telephone :** `+213 549 777 366`
*   **Depot GitHub Officiel :** [https://github.com/MGhemri/Ocularis-AI](https://github.com/MGhemri/Ocularis-AI)

**Copyright (c) 2026 Ghemri M — Licence MIT — Tous droits reserves.**
