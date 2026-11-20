"""
OCULARIS AI - MOTEUR D'ANALYSE FORENSIQUE & SURVEILLANCE RTSP (BACKEND)
Version 1.2.0 - Grade Industriel - Optimisé GPU NVIDIA RTX / CUDA
Détection intelligente, Multi-Object Tracking (ByteTrack), Anti-Flooding & Caméras IP
Système Universel d'Analyse Forensique Vidéo & Audit CCTV
Développeur : Ghemri M (contact@connect-gm.com / +213 549 777 366)
"""

import os
import cv2
import sys
import time
import math
import hashlib
import logging
import sqlite3
import datetime
import urllib.request
import urllib.parse
from pathlib import Path
from tqdm import tqdm

# --- CONFIGURATION ---
VIDEO_FOLDER = os.getenv("OCULARIS_VIDEO_FOLDER", os.getenv("GM_VIDEO_FOLDER", "./videos_source"))
OUTPUT_FOLDER = os.getenv("OCULARIS_OUTPUT_FOLDER", os.getenv("GM_OUTPUT_FOLDER", "./resultats_enquete"))
DB_PATH = f"{OUTPUT_FOLDER}/evidence_db.sqlite"
MODEL_SIZE = os.getenv("OCULARIS_MODEL_SIZE", os.getenv("GM_MODEL_SIZE", "yolov8m.pt"))
FRAME_SKIP = int(os.getenv("OCULARIS_FRAME_SKIP", os.getenv("GM_FRAME_SKIP", "10")))           # Analyse 1 image toutes les X frames
CONF_THRESHOLD = float(os.getenv("OCULARIS_CONF_THRESHOLD", os.getenv("GM_CONF_THRESHOLD", "0.40"))) # Seuil de confiance minimal

# Seuil de surface relative minimale pour les objets suspects (0.005 = 0.5% de l'image)
MIN_OBJECT_AREA_RATIO = float(os.getenv("OCULARIS_MIN_OBJ_RATIO", os.getenv("GM_MIN_OBJ_RATIO", "0.005")))

# Distance maximale (pixels) pour associer une personne à un objet transporté
PERSON_OBJ_MAX_DISTANCE_PX = int(os.getenv("OCULARIS_PROXIMITY_PX", os.getenv("GM_PROXIMITY_PX", "220")))

# Cooldown anti-flooding (secondes) pour éviter de saturer la DB d'alertes répétitives
COOLDOWN_SECONDS = float(os.getenv("OCULARIS_COOLDOWN_SEC", os.getenv("GM_COOLDOWN_SEC", "3.5")))

# Classes COCO ciblées :
# 0: Personne
# 1: Vélo, 2: Voiture, 3: Moto, 5: Bus, 7: Camion (Véhicules)
# 24: Sac à dos, 26: Sac à main, 28: Valise, 62: TV/Écran, 63: PC Portable (Objets lourds / Valeur)
CLASS_PERSON = 0
CLASSES_VEHICLES = {1, 2, 3, 5, 7}
CLASSES_SUSPECT_OBJECTS = {24, 26, 28, 62, 63}
TARGET_CLASSES = [0, 1, 2, 3, 5, 7, 24, 26, 28, 62, 63]

# Configuration Telegram optionnelle
TELEGRAM_ENABLED = os.getenv("OCULARIS_TELEGRAM_ALERTS", os.getenv("GM_TELEGRAM_ALERTS", "0")) in ("1", "true", "True")
TELEGRAM_BOT_TOKEN = os.getenv("OCULARIS_TELEGRAM_BOT_TOKEN", os.getenv("GM_TELEGRAM_BOT_TOKEN", "8921093269:AAGsbCCLF_MJMmtCTJ2mNfuKN_7d6UlClSA"))
TELEGRAM_CHAT_ID = os.getenv("OCULARIS_TELEGRAM_CHAT_ID", os.getenv("GM_TELEGRAM_CHAT_ID", "929293966"))

# --- SETUP DOSSIERS ---
Path(VIDEO_FOLDER).mkdir(parents=True, exist_ok=True)
Path(f"{OUTPUT_FOLDER}/snapshots").mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("Ocularis-AI")


def init_db():
    """Initialise la base de données SQLite en mode WAL avec le schéma forensique enrichi."""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE,
            status TEXT,
            processed_date DATETIME,
            total_frames INTEGER DEFAULT 0,
            fps REAL DEFAULT 25.0,
            sha256 TEXT DEFAULT ''
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            timestamp_str TEXT,
            frame_id INTEGER,
            obj_class TEXT,
            confidence REAL,
            count_people INTEGER,
            snapshot_path TEXT,
            is_suspicious BOOLEAN,
            severity TEXT DEFAULT 'SUSPICIOUS',
            track_id INTEGER DEFAULT NULL,
            qualification TEXT DEFAULT 'A_VERIFIER',
            notes TEXT DEFAULT '',
            FOREIGN KEY(video_id) REFERENCES videos(id)
        )
    ''')

    # Migration additive sécurisée si des tables existent déjà
    for col, col_type in [
        ("severity", "TEXT DEFAULT 'SUSPICIOUS'"),
        ("track_id", "INTEGER DEFAULT NULL"),
        ("qualification", "TEXT DEFAULT 'A_VERIFIER'"),
        ("notes", "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    for col, col_type in [
        ("total_frames", "INTEGER DEFAULT 0"),
        ("fps", "REAL DEFAULT 25.0"),
        ("sha256", "TEXT DEFAULT ''"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE videos ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    return conn


def calculate_file_hash(filepath, block_size=65536):
    """Calcule l'empreinte SHA-256 d'un fichier pour la garantie d'intégrité forensique."""
    sha = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                sha.update(block)
        return sha.hexdigest()
    except Exception as e:
        logger.warning(f"Impossible de calculer le SHA-256 pour {filepath}: {e}")
        return ""


def send_telegram_alert(video_name, timestamp_str, severity, obj_classes, person_count, snapshot_path):
    """Envoie une alerte avec photo vers le bot Telegram GM-Connect (opt-in)."""
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN:
        return

    try:
        caption = (
            f"<b>Ocularis AI — Alerte {severity}</b>\n"
            f"<b>Camera :</b> <code>{video_name}</code>\n"
            f"<b>Horodatage :</b> {timestamp_str}\n"
            f"<b>Personnes :</b> {person_count}\n"
            f"<b>Objets :</b> {obj_classes}\n"
            f"<i>Ocularis AI Surveillance CCTV</i>"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        
        full_snap_path = Path(OUTPUT_FOLDER) / "snapshots" / snapshot_path
        if not full_snap_path.exists():
            return

        with open(full_snap_path, 'rb') as img_f:
            img_data = img_f.read()

        boundary = '----WebKitFormBoundaryGMSurveillance'
        body = []
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{TELEGRAM_CHAT_ID}'.encode())
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}'.encode())
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="parse_mode"\r\n\r\nHTML'.encode())
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="photo"; filename="{snapshot_path}"\r\nContent-Type: image/jpeg\r\n'.encode())
        body.append(img_data)
        body.append(f'--{boundary}--\r\n'.encode())

        data = b'\r\n'.join(body)
        req = urllib.request.Request(url, data=data)
        req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
        with urllib.request.urlopen(req, timeout=8) as response:
            pass
        logger.info(f"[TELEGRAM] Alerte transmise pour {video_name} ({timestamp_str})")
    except Exception as e:
        logger.warning(f"Echec envoi Telegram: {e}")


def check_person_object_proximity(person_boxes, object_boxes, max_distance_px):
    """
    Vérifie si au moins un objet lourd/suspect est spatialement associé à une personne.
    Retourne True si un objet chevauche ou se trouve à proximité immédiate d'une personne.
    """
    for (px1, py1, px2, py2) in person_boxes:
        pcx = (px1 + px2) / 2.0
        pcy = (py1 + py2) / 2.0
        for (ox1, oy1, ox2, oy2) in object_boxes:
            ocx = (ox1 + ox2) / 2.0
            ocy = (oy1 + oy2) / 2.0

            # 1. Chevauchement direct des boîtes englobantes
            overlap_x = max(0, min(px2, ox2) - max(px1, ox1))
            overlap_y = max(0, min(py2, oy2) - max(py1, oy1))
            if overlap_x > 0 and overlap_y > 0:
                return True

            # 2. Proximité euclidienne des centres
            dist = math.hypot(pcx - ocx, pcy - ocy)
            if dist <= max_distance_px:
                return True
    return False


def analyze_videos():
    """Exécute l'analyse vidéo forensique complète optimisée pour GPU CUDA et flux CCTV."""
    try:
        import torch
        device = '0' if torch.cuda.is_available() else 'cpu'
        gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    except Exception:
        device = 'cpu'
        gpu_name = "CPU"

    logger.info(f"[INIT] DEMARRAGE MOTEUR SUR : {device.upper()} ({gpu_name})")

    # Vérification du fichier de poids local YOLO
    model_path = Path(MODEL_SIZE)
    if not model_path.exists():
        logger.error(f"[ERREUR] Modele '{MODEL_SIZE}' introuvable a la racine du projet.")
        logger.error("Telechargez le fichier de poids (yolov8m.pt) et placez-le dans le dossier du projet.")
        return

    try:
        from ultralytics import YOLO
        model = YOLO(MODEL_SIZE)
    except Exception as e:
        logger.error(f"[ERREUR] Erreur chargement Ultralytics YOLO: {e}")
        return

    conn = init_db()
    cursor = conn.cursor()

    # Scan récursif pour supporter les sous-dossiers NVR (ex: Cam_01/2026-11-20/file.dav)
    extensions = {'.mp4', '.avi', '.mkv', '.mov', '.dav', '.m4v'}
    video_files = []
    base_folder = Path(VIDEO_FOLDER)
    for p in base_folder.rglob('*'):
        if p.is_file() and p.suffix.lower() in extensions:
            video_files.append(p)

    if not video_files:
        logger.warning(f"[AVERTISSEMENT] Aucune video trouvee dans {VIDEO_FOLDER} (formats supportes: .mp4, .avi, .mkv, .mov, .dav)")
        conn.close()
        return

    logger.info(f"[INFO] {len(video_files)} video(s) identifiee(s) pour analyse.")

    for video_path in video_files:
        # Chemin relatif propre pour identifier la caméra et la date
        try:
            v_name = str(video_path.relative_to(base_folder)).replace("\\", "/")
        except ValueError:
            v_name = video_path.name

        # Vérification statut en base
        cursor.execute("SELECT id, status FROM videos WHERE filename=?", (v_name,))
        row = cursor.fetchone()

        if row and row[1] == 'COMPLETED':
            logger.info(f"[SKIP] '{v_name}' deja traite avec succes.")
            continue

        # Gestion de reprise après crash ou statut PROCESSING interrompu
        if row and row[1] == 'PROCESSING':
            video_db_id = row[0]
            logger.info(f"[REPRISE] Nettoyage des evenements partiels precedents pour '{v_name}' (ID: {video_db_id})...")
            cursor.execute("DELETE FROM events WHERE video_id=?", (video_db_id,))
            cursor.execute("UPDATE videos SET status='PROCESSING', processed_date=? WHERE id=?", 
                           (datetime.datetime.now(), video_db_id))
            conn.commit()
        else:
            file_hash = calculate_file_hash(video_path)
            cursor.execute(
                "INSERT INTO videos (filename, status, processed_date, sha256) VALUES (?, 'PROCESSING', ?, ?)",
                (v_name, datetime.datetime.now(), file_hash)
            )
            video_db_id = cursor.lastrowid
            conn.commit()

        # Ouverture flux vidéo avec OpenCV
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error(f"[ERREUR] Impossible d'ouvrir la video : {video_path}")
            cursor.execute("UPDATE videos SET status='ERROR' WHERE id=?", (video_db_id,))
            conn.commit()
            continue

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0.0 or math.isnan(fps):
            fps = 25.0

        cursor.execute("UPDATE videos SET total_frames=?, fps=? WHERE id=?", (max(0, total_frames), fps, video_db_id))
        conn.commit()

        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        frame_area = frame_w * frame_h
        min_obj_pixels = frame_area * MIN_OBJECT_AREA_RATIO

        logger.info(f"[ANALYSE] '{v_name}' | FPS: {fps:.1f} | Resolution: {frame_w}x{frame_h} | Frames estimees: {total_frames if total_frames > 0 else 'Inconnue'}")
        pbar = tqdm(total=total_frames if total_frames > 0 else None, unit="img", desc=Path(v_name).name[:20])

        current_frame_id = 0
        last_alert_ts = -999.0
        last_alert_type = ""

        # Déterminer si ByteTrack est disponible
        use_tracking = True

        while cap.isOpened():
            # ENG-01 : Saut rapide séquentiel par cap.grab() sans décompression lourde
            for _ in range(FRAME_SKIP - 1):
                if not cap.grab():
                    break
                current_frame_id += 1
                pbar.update(1)

            # Lecture et décodage de la frame cible
            success, frame = cap.read()
            if not success or frame is None:
                break

            current_frame_id += 1
            pbar.update(1)

            # INFERENCE IA (Tracking multi-objets ByteTrack avec fallback gracieux)
            results = None
            if use_tracking:
                try:
                    results = model.track(
                        frame,
                        persist=True,
                        classes=TARGET_CLASSES,
                        conf=CONF_THRESHOLD,
                        verbose=False,
                        device=device,
                        tracker="bytetrack.yaml"
                    )
                except Exception as track_err:
                    logger.debug(f"ByteTrack indisponible, fallback standard : {track_err}")
                    use_tracking = False

            if results is None:
                results = model(frame, classes=TARGET_CLASSES, conf=CONF_THRESHOLD, verbose=False, device=device)

            detected_objs = []
            person_boxes = []
            suspect_obj_boxes = []
            vehicle_boxes = []
            person_count = 0
            max_conf = 0.0
            primary_track_id = None

            if results and len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    label = model.names.get(cls_id, str(cls_id))
                    conf = float(box.conf[0])
                    if conf > max_conf:
                        max_conf = conf

                    detected_objs.append(label)

                    # Coordonnées pixel [x1, y1, x2, y2]
                    xyxy = box.xyxy[0].cpu().numpy() if hasattr(box.xyxy[0], 'cpu') else box.xyxy[0]
                    bx1, by1, bx2, by2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                    box_area = (bx2 - bx1) * (by2 - by1)

                    # Récupération du track_id si disponible
                    if hasattr(box, 'id') and box.id is not None:
                        t_id = int(box.id[0])
                        if primary_track_id is None:
                            primary_track_id = t_id

                    if cls_id == CLASS_PERSON:
                        person_count += 1
                        person_boxes.append((bx1, by1, bx2, by2))
                    elif cls_id in CLASSES_VEHICLES:
                        vehicle_boxes.append((bx1, by1, bx2, by2))
                    elif cls_id in CLASSES_SUSPECT_OBJECTS:
                        # Filtrage de surface minimale relative (évite les faux positifs sur petits objets)
                        if box_area >= min_obj_pixels:
                            suspect_obj_boxes.append((bx1, by1, bx2, by2))

            # RÈGLES DE DÉCLENCHEMENT INTELLIGENTES & CLASSIFICATION DE SÉVÉRITÉ
            is_alert = False
            severity = "SUSPICIOUS"
            alert_reason = ""

            # 1. RÈGLE CRITIQUE : Personne transportant / manipulant un objet lourd ou de valeur (TV, Valise, PC...)
            if person_count >= 1 and len(suspect_obj_boxes) > 0:
                is_near = check_person_object_proximity(person_boxes, suspect_obj_boxes, PERSON_OBJ_MAX_DISTANCE_PX)
                if is_near:
                    is_alert = True
                    severity = "CRITICAL"
                    alert_reason = "PERSON_WITH_VALUABLE_OBJECT"

            # 2. RÈGLE SUSPECT : Attroupement / Groupe suspect (>= 3 personnes)
            if not is_alert and person_count >= 3:
                is_alert = True
                severity = "SUSPICIOUS"
                alert_reason = "SUSPICIOUS_GROUP"

            # 3. RÈGLE VÉHICULE : Véhicule présent dans la zone surveillée
            if not is_alert and len(vehicle_boxes) > 0:
                is_alert = True
                severity = "INFO"
                alert_reason = "VEHICLE_DETECTED"

            # GESTION DU COOLDOWN ANTI-FLOODING (ENG-02)
            current_video_sec = current_frame_id / fps
            if is_alert:
                time_since_last = current_video_sec - last_alert_ts
                is_same_type = (alert_reason == last_alert_type)

                # Si c'est la même scène continue, on applique le cooldown
                if is_same_type and time_since_last < COOLDOWN_SECONDS:
                    # Ne pas dupliquer en continu
                    is_alert = False
                else:
                    last_alert_ts = current_video_sec
                    last_alert_type = alert_reason

            if is_alert:
                ts_str = str(datetime.timedelta(seconds=int(current_video_sec)))
                img_name = f"v{video_db_id}_f{current_frame_id}.jpg"
                img_path = f"{OUTPUT_FOLDER}/snapshots/{img_name}"

                # Sauvegarde du snapshot annoté avec bounding boxes et labels
                annotated_frame = results[0].plot() if results else frame
                cv2.imwrite(img_path, annotated_frame)

                unique_classes = sorted(list(set(detected_objs)))
                classes_str = ", ".join(unique_classes)

                # Sauvegarde dans evidence_db.sqlite
                cursor.execute('''
                    INSERT INTO events (
                        video_id, timestamp_str, frame_id, obj_class, 
                        count_people, snapshot_path, confidence, is_suspicious, 
                        severity, track_id, qualification, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'A_VERIFIER', '')
                ''', (
                    video_db_id, ts_str, current_frame_id, classes_str,
                    person_count, img_name, max_conf, 1,
                    severity, primary_track_id
                ))
                conn.commit()

                # Dispatch Telegram si activé (uniquement alertes CRITICAL ou SUSPICIOUS)
                if severity in ("CRITICAL", "SUSPICIOUS"):
                    send_telegram_alert(
                        video_name=v_name,
                        timestamp_str=ts_str,
                        severity=severity,
                        obj_classes=classes_str,
                        person_count=person_count,
                        snapshot_path=img_name
                    )

        cap.release()
        cursor.execute("UPDATE videos SET status='COMPLETED' WHERE id=?", (video_db_id,))
        conn.commit()
        pbar.close()
        logger.info(f"[OK] Video terminee : '{v_name}' (Total frames traitees : {current_frame_id})")

    conn.close()
    logger.info("[COMPLET] Toutes les analyses de fichiers sont terminees.")


def run_live_rtsp():
    """Démarre la surveillance continue des flux RTSP multi-caméras en console."""
    logger.info("[INIT] Demarrage du module de surveillance RTSP en direct...")
    try:
        from rtsp_manager import MultiCameraRTSPManager
        manager = MultiCameraRTSPManager.get_instance()
    except Exception as e:
        logger.error(f"[ERREUR] Impossible d'initialiser le gestionnaire RTSP : {e}")
        return

    logger.info("[ACTIF] Surveillance des flux RTSP (cameras.json). Appuyez sur Ctrl+C pour arreter.")
    try:
        last_report = time.time()
        while True:
            time.sleep(2.0)
            now = time.time()
            if now - last_report >= 10.0:
                cams = manager.get_cameras_list(mask_secret=True)
                active = [c for c in cams if c['enabled']]
                live = [c for c in active if c['status'] == 'LIVE']
                logger.info(f"[ETAT RTSP] : {len(live)}/{len(active)} flux en direct actif(s) | Total configure : {len(cams)}")
                for c in active:
                    logger.info(f"   [{c['id']}] {c['name']} : {c['status']} ({c['fps_actual']} FPS, {c['total_events']} alertes)")
                last_report = now
    except KeyboardInterrupt:
        logger.info("[ARRET] Arret de la surveillance RTSP demande.")
        manager.stop_all()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ocularis AI - Moteur Forensique & Surveillance RTSP")
    parser.add_argument("--live", action="store_true", help="Démarrer la surveillance continue des flux RTSP (cameras.json)")
    parser.add_argument("--batch", action="store_true", help="Analyser uniquement les fichiers du dossier videos_source/")
    args = parser.parse_args()

    if args.live:
        run_live_rtsp()
    else:
        analyze_videos()
