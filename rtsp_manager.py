"""
OCULARIS AI - GESTIONNAIRE DE FLUX RTSP & CAMÉRAS IP EN DIRECT
Version 1.2.0 - Grade Industriel - Surveillance Temps Réel Multi-Caméras
Ingestion Bufferless Zero-Latence, Auto-Reconnexion, Inférence YOLOv8 + ByteTrack
Système Universel d'Analyse Forensique Vidéo & Audit CCTV
Développeur : Ghemri M (contact@connect-gm.com)
"""

import os
import re
import sys
import time
import json
import math
import logging
import sqlite3
import datetime
import threading
from pathlib import Path

# Tentative d'import conditionnelle de cv2 et numpy avec fallbacks gracieux
try:
    import cv2
except ImportError:
    cv2 = None

try:
    import numpy as np
except ImportError:
    np = None

# Configuration FFMPEG pour OpenCV : forcer le transport TCP pour éviter les pertes de paquets RTSP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;1500000|probesize;1500000"

logger = logging.getLogger("Ocularis-RTSP")

# Constantes et répertoires par défaut
OUTPUT_FOLDER = os.getenv("OCULARIS_OUTPUT_FOLDER", os.getenv("GM_OUTPUT_FOLDER", "./resultats_enquete"))
DB_PATH = f"{OUTPUT_FOLDER}/evidence_db.sqlite"
CONFIG_FILE = os.getenv("OCULARIS_CAMERAS_CONFIG", "./cameras.json")
MODEL_SIZE = os.getenv("OCULARIS_MODEL_SIZE", os.getenv("GM_MODEL_SIZE", "yolov8m.pt"))

# Classes COCO ciblées pour l'IA
CLASS_PERSON = 0
CLASSES_VEHICLES = {1, 2, 3, 5, 7}
CLASSES_SUSPECT_OBJECTS = {24, 26, 28, 62, 63, 67}
TARGET_CLASSES = [0, 1, 2, 3, 5, 7, 24, 26, 28, 62, 63, 67]

# Dictionnaire exhaustif des cibles sélectionnables depuis l'interface web
SUPPORTED_DETECTION_CLASSES = {
    'person': 0,
    'bicycle': 1,
    'car': 2,
    'motorcycle': 3,
    'bus': 5,
    'truck': 7,
    'cat': 15,
    'dog': 16,
    'backpack': 24,
    'handbag': 26,
    'suitcase': 28,
    'tv': 62,
    'laptop': 63,
    'cell phone': 67
}

DEFAULT_TARGET_CLASSES = [
    'person', 'backpack', 'handbag', 'suitcase',
    'cell phone', 'laptop', 'tv', 'car', 'motorcycle', 'bicycle'
]

# Seuils par défaut
CONF_THRESHOLD = float(os.getenv("OCULARIS_CONF_THRESHOLD", os.getenv("GM_CONF_THRESHOLD", "0.40")))
MIN_OBJECT_AREA_RATIO = float(os.getenv("OCULARIS_MIN_OBJ_RATIO", os.getenv("GM_MIN_OBJ_RATIO", "0.005")))
PERSON_OBJ_MAX_DISTANCE_PX = int(os.getenv("OCULARIS_PROXIMITY_PX", os.getenv("GM_PROXIMITY_PX", "220")))

# Configuration Telegram optionnelle
TELEGRAM_ENABLED = os.getenv("OCULARIS_TELEGRAM_ALERTS", os.getenv("GM_TELEGRAM_ALERTS", "0")) in ("1", "true", "True")
TELEGRAM_BOT_TOKEN = os.getenv("OCULARIS_TELEGRAM_BOT_TOKEN", os.getenv("GM_TELEGRAM_BOT_TOKEN", "8921093269:AAGsbCCLF_MJMmtCTJ2mNfuKN_7d6UlClSA"))
TELEGRAM_CHAT_ID = os.getenv("OCULARIS_TELEGRAM_CHAT_ID", os.getenv("GM_TELEGRAM_CHAT_ID", "929293966"))


def mask_rtsp_password(url: str) -> str:
    """Masque le mot de passe d'une URL RTSP/HTTP pour l'affichage public/API."""
    if not url:
        return ""
    # Motif: rtsp://username:password@host
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:******@', url)


def unmask_rtsp_password(new_url: str, old_url: str) -> str:
    """Conserve l'ancien mot de passe si l'utilisateur soumet une URL avec '******'."""
    if "******" in new_url and old_url:
        old_match = re.search(r'://([^:]+):([^@]+)@', old_url)
        new_match = re.search(r'://([^:]+):\*{6}@', new_url)
        if old_match and new_match:
            old_user, old_pass = old_match.group(1), old_match.group(2)
            new_user = new_match.group(1)
            if new_user == old_user:
                return new_url.replace(f":******@", f":{old_pass}@")
    return new_url


def create_placeholder_frame(title: str, subtitle: str = "", width=640, height=360):
    """Crée une image de substitution élégante (dark theme) si le flux est hors ligne."""
    if np is None or cv2 is None:
        return None
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = (30, 41, 59)  # Slate dark #1e293b

    # Ligne d'accent supérieure
    cv2.rectangle(frame, (0, 0), (width, 4), (220, 53, 69), -1)

    # Textes
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, title, (30, int(height * 0.45)), font, 0.7, (241, 245, 249), 2, cv2.LINE_AA)
    if subtitle:
        cv2.putText(frame, subtitle, (30, int(height * 0.60)), font, 0.45, (148, 163, 184), 1, cv2.LINE_AA)
    return frame


def check_person_object_proximity(person_boxes, object_boxes, max_distance_px):
    """Vérifie si un objet lourd ou de valeur est spatialement associé à une personne."""
    for (px1, py1, px2, py2) in person_boxes:
        pcx = (px1 + px2) / 2.0
        pcy = (py1 + py2) / 2.0
        for (ox1, oy1, ox2, oy2) in object_boxes:
            ocx = (ox1 + ox2) / 2.0
            ocy = (oy1 + oy2) / 2.0

            # 1. Chevauchement direct
            overlap_x = max(0, min(px2, ox2) - max(px1, ox1))
            overlap_y = max(0, min(py2, oy2) - max(py1, oy1))
            if overlap_x > 0 and overlap_y > 0:
                return True

            # 2. Distance euclidienne entre centres
            dist = math.hypot(pcx - ocx, pcy - ocy)
            if dist <= max_distance_px:
                return True
    return False


def is_webcam_source(source):
    """
    Détermine si la source correspond à une webcam locale (entier ou chaîne numérique).
    Retourne (is_webcam: bool, normalized_source: int | str).
    """
    try:
        if isinstance(source, int):
            return True, source
        s = str(source).strip()
        if s.isdigit():
            return True, int(s)
    except (ValueError, TypeError):
        pass
    return False, str(source).strip()


def open_video_capture(source):
    """
    Ouvre une capture vidéo avec le backend adapté selon la source :
    - Entier ou chiffres (ex: 0, 1) -> Webcam intégrée ou USB (DirectShow sous Windows)
    - URL RTSP / HTTP ou chemin fichier -> Backend FFMPEG optimisé bufferless
    """
    if cv2 is None:
        return None, False

    is_webcam, source_val = is_webcam_source(source)

    if is_webcam:
        backend = cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY
        cap = cv2.VideoCapture(source_val, backend)
        if not cap.isOpened() and os.name == 'nt':
            cap = cv2.VideoCapture(source_val)
        return cap, True
    else:
        # Optimisation timeout et transport TCP sous FFmpeg
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;4000000"
        cap = cv2.VideoCapture(str(source_val), cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap, False


def test_rtsp_connection(url: str, timeout: float = 3.5):
    """
    Teste la connectivité d'une URL RTSP, flux IP ou webcam locale.
    Retourne un dictionnaire {'success': bool, 'width': int, 'height': int, 'fps': float, 'error': str}.
    """
    if cv2 is None:
        return {'success': False, 'error': "OpenCV (cv2) n'est pas installe dans cet environnement."}

    cap = None
    start_time = time.time()
    try:
        cap, is_webcam = open_video_capture(url)
        if cap is None:
            return {'success': False, 'error': "Echec de creation du flux OpenCV."}

        while (time.time() - start_time) < timeout:
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    h, w = frame.shape[:2]
                    raw_fps = cap.get(cv2.CAP_PROP_FPS)
                    fps = raw_fps if (raw_fps is not None and raw_fps > 0) else 30.0
                    cap.release()
                    return {
                        'success': True,
                        'width': w,
                        'height': h,
                        'fps': round(fps, 1),
                        'error': None
                    }
            time.sleep(0.15)

        if cap:
            cap.release()
        return {'success': False, 'error': f"Delai d'attente depasse ({timeout}s) sans reception d'image valide."}
    except Exception as e:
        if cap:
            try:
                cap.release()
            except Exception:
                pass
        return {'success': False, 'error': str(e)}


class RTSPStreamReader:
    """
    Lecteur de flux RTSP / IP multi-threadé avec ingestion bufferless.
    Garantit zéro latence d'accumulation et auto-reconnexion continue en cas de coupure réseau.
    """

    def __init__(self, camera_id: str, name: str, url: str, enabled: bool = True,
                 fps_analyze: float = 2.0, cooldown_sec: float = 3.5,
                 conf_threshold: float = 0.35, trigger_mode: str = "ANY_TARGET",
                 target_classes: list = None):
        self.camera_id = camera_id
        self.name = name
        self.url = url
        self.enabled = enabled
        self.fps_analyze = max(0.5, float(fps_analyze))
        self.cooldown_sec = max(0.5, float(cooldown_sec))
        self.conf_threshold = max(0.15, min(0.95, float(conf_threshold)))
        self.trigger_mode = trigger_mode if trigger_mode in ("ANY_TARGET", "FORENSIC") else "ANY_TARGET"
        self.target_classes = list(target_classes) if target_classes is not None else list(DEFAULT_TARGET_CLASSES)

        self.status = "STOPPED"  # STOPPED, CONNECTING, LIVE, RECONNECTING, ERROR
        self.error_message = ""
        self.fps_actual = 0.0
        self.total_frames_read = 0
        self.resolution = (0, 0)

        # Buffers d'images sécurisés par verrou
        self.lock = threading.Lock()
        self.last_raw_frame = None
        self.last_annotated_frame = None
        self.last_frame_time = 0.0

        # Suivi forensique d'analyse
        self.last_inference_time = 0.0
        self.last_alert_time = -999.0
        self.last_alert_reason = ""
        self.total_events = 0

        self.running = False
        self.thread = None

    def start(self):
        """Démarre le thread de capture continue."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._capture_worker, name=f"RTSP-{self.camera_id}", daemon=True)
        self.thread.start()
        logger.info(f"[INFO] Demarrage du thread de capture pour '{self.name}' ({self.camera_id})")

    def stop(self):
        """Arrête proprement le thread de capture."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.status = "STOPPED"
        logger.info(f"[INFO] Arret du thread de capture pour '{self.name}' ({self.camera_id})")

    def _capture_worker(self):
        """Boucle de capture d'images bufferless avec auto-reconnexion."""
        if cv2 is None:
            self.status = "ERROR"
            self.error_message = "Module OpenCV non disponible."
            return

        source = int(self.url) if str(self.url).isdigit() else str(self.url)

        while self.running:
            if not self.enabled:
                self.status = "STOPPED"
                time.sleep(1.0)
                continue

            self.status = "CONNECTING"
            self.error_message = ""
            cap = None

            try:
                cap, is_webcam = open_video_capture(self.url)

                if cap is None or not cap.isOpened():
                    self.status = "RECONNECTING"
                    self.error_message = "Echec d'ouverture du flux (camera ou webcam)."
                    time.sleep(3.0)
                    continue

                self.status = "LIVE"
                frames_in_sec = 0
                last_fps_eval = time.time()

                while self.running and self.enabled and cap.isOpened():
                    # Ingestion bufferless : grab() rapide sans décompression inutile
                    grabbed = cap.grab()
                    if not grabbed:
                        break

                    ret, frame = cap.retrieve()
                    if not ret or frame is None:
                        break

                    now = time.time()
                    with self.lock:
                        self.last_raw_frame = frame
                        self.last_frame_time = now
                        self.total_frames_read += 1
                        frames_in_sec += 1
                        if self.resolution == (0, 0):
                            self.resolution = (frame.shape[1], frame.shape[0])

                    # Calcul du FPS réel mesuré
                    elapsed = now - last_fps_eval
                    if elapsed >= 1.0:
                        self.fps_actual = round(frames_in_sec / elapsed, 1)
                        frames_in_sec = 0
                        last_fps_eval = now

            except Exception as e:
                self.error_message = str(e)
                logger.warning(f"[AVERTISSEMENT] Erreur capture sur '{self.name}' : {e}")
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

            if self.running and self.enabled:
                self.status = "RECONNECTING"
                time.sleep(3.0)

        self.status = "STOPPED"

    def get_latest_frame(self, annotated: bool = True):
        """Retourne une copie de la dernière image disponible sous verrou."""
        with self.lock:
            if annotated and self.last_annotated_frame is not None:
                return self.last_annotated_frame.copy()
            if self.last_raw_frame is not None:
                return self.last_raw_frame.copy()
            return None

    def update_annotated_frame(self, frame):
        """Met à jour l'image annotée par l'IA."""
        with self.lock:
            self.last_annotated_frame = frame

    def to_dict(self, mask_secret: bool = True):
        """Sérialise l'état de la caméra pour l'API REST."""
        display_url = mask_rtsp_password(self.url) if mask_secret else self.url
        return {
            'id': self.camera_id,
            'name': self.name,
            'url': display_url,
            'enabled': self.enabled,
            'fps_analyze': self.fps_analyze,
            'cooldown_sec': self.cooldown_sec,
            'conf_threshold': self.conf_threshold,
            'trigger_mode': self.trigger_mode,
            'target_classes': self.target_classes,
            'status': self.status,
            'error_message': self.error_message,
            'fps_actual': self.fps_actual,
            'total_frames': self.total_frames_read,
            'resolution': f"{self.resolution[0]}x{self.resolution[1]}" if self.resolution != (0, 0) else "Inconnue",
            'total_events': self.total_events,
            'last_frame_time': self.last_frame_time
        }


class MultiCameraRTSPManager:
    """
    Gestionnaire centralisé des flux RTSP multi-caméras pour Ocularis AI.
    Pilote le cycle de vie des flux, la persistance de configuration (cameras.json),
    le moteur d'inférence temps réel YOLOv8 et le streaming MJPEG web.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Singleton thread-safe pour partage entre web_interface et ai_engine."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self, config_path: str = CONFIG_FILE):
        self.config_path = Path(config_path)
        self.streams = {}  # {camera_id: RTSPStreamReader}
        self.streams_lock = threading.Lock()

        # État du modèle d'inférence IA
        self.model = None
        self.device = 'cpu'
        self.ai_running = False
        self.ai_thread = None

        self._ensure_default_config()
        self.load_configuration()
        self.start_all_enabled()
        self.start_ai_worker()

    def _ensure_default_config(self):
        """Génère un fichier cameras.json par défaut avec exemples si inexistant."""
        if not self.config_path.exists():
            default_cameras = [
                {
                    "id": "cam_01",
                    "name": "Caméra 01 - Entrée Principale",
                    "url": "rtsp://admin:admin123@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0",
                    "enabled": False,
                    "fps_analyze": 2.0,
                    "cooldown_sec": 3.5
                },
                {
                    "id": "cam_02",
                    "name": "Caméra 02 - Parking & Périmètre",
                    "url": "rtsp://admin:admin123@192.168.1.101:554/h264Preview_01_main",
                    "enabled": False,
                    "fps_analyze": 2.0,
                    "cooldown_sec": 3.5
                },
                {
                    "id": "cam_03",
                    "name": "Caméra 03 - Entrepôt & Dépôt",
                    "url": "rtsp://admin:admin123@192.168.1.102:554/live/ch0",
                    "enabled": False,
                    "fps_analyze": 2.0,
                    "cooldown_sec": 3.5
                }
            ]
            try:
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_cameras, f, indent=2, ensure_ascii=False)
                logger.info(f"[INFO] Fichier de configuration cree : {self.config_path}")
            except Exception as e:
                logger.error(f"Impossible de créer le fichier de config par défaut : {e}")

    def load_configuration(self):
        """Charge les caméras depuis cameras.json et initialise les lecteurs de flux."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Erreur de lecture de {self.config_path} : {e}")
            return

        with self.streams_lock:
            existing_ids = set(self.streams.keys())
            loaded_ids = set()

            for item in data:
                cam_id = item.get("id")
                if not cam_id:
                    continue
                loaded_ids.add(cam_id)

                name = item.get("name", f"Caméra {cam_id}")
                url = item.get("url", "")
                enabled = bool(item.get("enabled", True))
                fps_analyze = float(item.get("fps_analyze", 2.0))
                cooldown_sec = float(item.get("cooldown_sec", 3.5))
                conf_threshold = float(item.get("conf_threshold", 0.35))
                trigger_mode = item.get("trigger_mode", "ANY_TARGET")
                target_classes = item.get("target_classes", None)

                if cam_id in self.streams:
                    # Mise à jour à chaud sans interrompre si l'URL n'a pas changé
                    stream = self.streams[cam_id]
                    stream.name = name
                    stream.fps_analyze = fps_analyze
                    stream.cooldown_sec = cooldown_sec
                    stream.conf_threshold = conf_threshold
                    stream.trigger_mode = trigger_mode
                    if target_classes is not None:
                        stream.target_classes = list(target_classes)
                    if stream.url != url:
                        stream.stop()
                        stream.url = url
                        if enabled:
                            stream.start()
                    elif stream.enabled != enabled:
                        stream.enabled = enabled
                        if enabled:
                            stream.start()
                        else:
                            stream.stop()
                else:
                    stream = RTSPStreamReader(
                        camera_id=cam_id,
                        name=name,
                        url=url,
                        enabled=enabled,
                        fps_analyze=fps_analyze,
                        cooldown_sec=cooldown_sec,
                        conf_threshold=conf_threshold,
                        trigger_mode=trigger_mode,
                        target_classes=target_classes
                    )
                    self.streams[cam_id] = stream

            # Supprimer les flux retirés du fichier
            for obsolete_id in existing_ids - loaded_ids:
                logger.info(f"Retrait de la caméra '{obsolete_id}'")
                self.streams[obsolete_id].stop()
                del self.streams[obsolete_id]

    def save_configuration(self):
        """Sauvegarde l'état actuel des caméras dans cameras.json."""
        with self.streams_lock:
            cameras_data = []
            for stream in self.streams.values():
                cameras_data.append({
                    "id": stream.camera_id,
                    "name": stream.name,
                    "url": stream.url,
                    "enabled": stream.enabled,
                    "fps_analyze": stream.fps_analyze,
                    "cooldown_sec": stream.cooldown_sec,
                    "conf_threshold": stream.conf_threshold,
                    "trigger_mode": stream.trigger_mode,
                    "target_classes": stream.target_classes
                })

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(cameras_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur de sauvegarde de {self.config_path} : {e}")

    def start_all_enabled(self):
        """Démarre toutes les caméras marquées actives."""
        with self.streams_lock:
            for stream in self.streams.values():
                if stream.enabled:
                    stream.start()

    def stop_all(self):
        """Arrête toutes les caméras."""
        with self.streams_lock:
            for stream in self.streams.values():
                stream.stop()

    def add_or_update_camera(self, data: dict) -> RTSPStreamReader:
        """Ajoute ou modifie une caméra."""
        cam_id = data.get("id")
        if not cam_id:
            raise ValueError("L'identifiant de caméra ('id') est obligatoire.")

        name = data.get("name", f"Caméra {cam_id}")
        raw_url = data.get("url", "").strip()
        enabled = bool(data.get("enabled", True))
        fps_analyze = float(data.get("fps_analyze", 2.0))
        cooldown_sec = float(data.get("cooldown_sec", 3.5))
        conf_threshold = float(data.get("conf_threshold", 0.35))
        trigger_mode = str(data.get("trigger_mode", "ANY_TARGET"))
        target_classes = data.get("target_classes", None)

        with self.streams_lock:
            old_url = self.streams[cam_id].url if cam_id in self.streams else ""
            url = unmask_rtsp_password(raw_url, old_url)

            if cam_id in self.streams:
                stream = self.streams[cam_id]
                stream.name = name
                stream.fps_analyze = fps_analyze
                stream.cooldown_sec = cooldown_sec
                stream.conf_threshold = conf_threshold
                stream.trigger_mode = trigger_mode
                if target_classes is not None:
                    stream.target_classes = list(target_classes)
                url_changed = (stream.url != url)
                stream.url = url
                stream.enabled = enabled
                if url_changed:
                    stream.stop()
                    if enabled:
                        stream.start()
                elif enabled and stream.status == "STOPPED":
                    stream.start()
                elif not enabled and stream.status != "STOPPED":
                    stream.stop()
            else:
                stream = RTSPStreamReader(
                    camera_id=cam_id,
                    name=name,
                    url=url,
                    enabled=enabled,
                    fps_analyze=fps_analyze,
                    cooldown_sec=cooldown_sec,
                    conf_threshold=conf_threshold,
                    trigger_mode=trigger_mode,
                    target_classes=target_classes
                )
                self.streams[cam_id] = stream
                if enabled:
                    stream.start()

        self.save_configuration()
        return stream

    def update_camera_classes(self, cam_id: str, data: dict) -> RTSPStreamReader:
        """Met à jour à chaud les cibles, seuils et modes d'une caméra."""
        with self.streams_lock:
            stream = self.streams.get(cam_id)
            if not stream:
                raise KeyError(f"Caméra '{cam_id}' introuvable.")

            if 'target_classes' in data and isinstance(data['target_classes'], list):
                cleaned = [c for c in data['target_classes'] if c in SUPPORTED_DETECTION_CLASSES]
                if cleaned:
                    stream.target_classes = cleaned
            if 'conf_threshold' in data:
                stream.conf_threshold = max(0.15, min(0.95, float(data['conf_threshold'])))
            if 'trigger_mode' in data:
                mode = str(data['trigger_mode'])
                if mode in ("ANY_TARGET", "FORENSIC"):
                    stream.trigger_mode = mode
            if 'fps_analyze' in data:
                stream.fps_analyze = max(0.5, min(10.0, float(data['fps_analyze'])))
            if 'cooldown_sec' in data:
                stream.cooldown_sec = max(0.5, min(30.0, float(data['cooldown_sec'])))

        self.save_configuration()
        return stream

    def toggle_camera(self, cam_id: str, enabled: bool = None) -> bool:
        """Active ou désactive une caméra."""
        with self.streams_lock:
            if cam_id not in self.streams:
                return False
            stream = self.streams[cam_id]
            if enabled is None:
                stream.enabled = not stream.enabled
            else:
                stream.enabled = enabled

            if stream.enabled:
                stream.start()
            else:
                stream.stop()

        self.save_configuration()
        return stream.enabled

    def delete_camera(self, cam_id: str) -> bool:
        """Supprime une caméra de la configuration."""
        with self.streams_lock:
            if cam_id not in self.streams:
                return False
            stream = self.streams.pop(cam_id)
            stream.stop()

        self.save_configuration()
        return True

    def get_cameras_list(self, mask_secret: bool = True) -> list:
        """Retourne la liste des caméras sérialisée."""
        with self.streams_lock:
            return [stream.to_dict(mask_secret=mask_secret) for stream in self.streams.values()]

    def get_camera(self, cam_id: str) -> RTSPStreamReader:
        with self.streams_lock:
            return self.streams.get(cam_id)

    # --- MOTEUR D'INFÉRENCE TEMPS RÉEL MULTI-CAMÉRAS ---

    def _ensure_model_loaded(self):
        """Charge le modèle YOLOv8 en mémoire s'il n'est pas déjà prêt."""
        if self.model is not None:
            return True

        model_file = Path(MODEL_SIZE)
        if not model_file.exists():
            logger.warning(f"[AVERTISSEMENT] Fichier de poids '{MODEL_SIZE}' introuvable pour l'inference en direct.")
            return False

        try:
            import torch
            from ultralytics import YOLO
            self.device = '0' if torch.cuda.is_available() else 'cpu'
            self.model = YOLO(str(model_file))
            logger.info(f"[INFO] Modele YOLOv8m charge pour surveillance en direct sur : {self.device.upper()}")
            return True
        except Exception as e:
            logger.error(f"[ERREUR] Erreur de chargement du modele YOLO : {e}")
            return False

    def start_ai_worker(self):
        """Démarre le thread d'analyse IA en arrière-plan."""
        if self.ai_running:
            return
        self.ai_running = True
        self.ai_thread = threading.Thread(target=self._ai_worker_loop, name="Ocularis-AI-Live", daemon=True)
        self.ai_thread.start()

    def _ai_worker_loop(self):
        """Boucle d'inférence périodique sur l'ensemble des flux caméras en direct."""
        while self.ai_running:
            # Récupération des flux actifs
            with self.streams_lock:
                active_streams = [s for s in self.streams.values() if s.enabled and s.status == "LIVE"]

            if not active_streams:
                time.sleep(0.5)
                continue

            if not self._ensure_model_loaded():
                time.sleep(2.0)
                continue

            now = time.time()
            for stream in active_streams:
                interval = 1.0 / stream.fps_analyze
                if (now - stream.last_inference_time) < interval:
                    continue

                frame = stream.get_latest_frame(annotated=False)
                if frame is None:
                    continue

                stream.last_inference_time = now

                # Inférence et détection
                try:
                    self._process_stream_frame(stream, frame)
                except Exception as e:
                    logger.warning(f"Erreur inférence sur '{stream.name}' : {e}")

            time.sleep(0.01)

    def _process_stream_frame(self, stream: RTSPStreamReader, frame):
        """Exécute YOLO + ByteTrack selon les classes configurées et enregistre les événements."""
        # Résolution dynamique des classes cibles sélectionnées pour cette caméra
        target_names = stream.target_classes if (hasattr(stream, 'target_classes') and stream.target_classes) else DEFAULT_TARGET_CLASSES
        active_class_ids = [SUPPORTED_DETECTION_CLASSES[name] for name in target_names if name in SUPPORTED_DETECTION_CLASSES]
        if not active_class_ids:
            active_class_ids = [0]  # Au moins personne par sécurité si tout est décoché

        conf = getattr(stream, 'conf_threshold', 0.35) or 0.35

        try:
            results = self.model.track(
                frame,
                persist=True,
                classes=active_class_ids,
                conf=conf,
                verbose=False,
                device=self.device,
                tracker="bytetrack.yaml"
            )
        except Exception:
            results = self.model(frame, classes=active_class_ids, conf=conf, verbose=False, device=self.device)

        if not results or len(results) == 0:
            return

        annotated_frame = results[0].plot()
        stream.update_annotated_frame(annotated_frame)

        detected_objs = []
        person_boxes = []
        suspect_obj_boxes = []
        vehicle_boxes = []
        person_count = 0
        max_conf = 0.0
        primary_track_id = None

        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_w * frame_h
        min_obj_pixels = frame_area * MIN_OBJECT_AREA_RATIO

        if results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                label = self.model.names.get(cls_id, str(cls_id))
                conf_val = float(box.conf[0])
                if conf_val > max_conf:
                    max_conf = conf_val

                detected_objs.append(label)

                xyxy = box.xyxy[0].cpu().numpy() if hasattr(box.xyxy[0], 'cpu') else box.xyxy[0]
                bx1, by1, bx2, by2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                box_area = (bx2 - bx1) * (by2 - by1)

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
                    if box_area >= min_obj_pixels:
                        suspect_obj_boxes.append((bx1, by1, bx2, by2))

        if not detected_objs:
            return

        # Règles de sévérité forensique et déclenchement selon le mode choisi
        is_alert = False
        severity = "INFO"
        alert_reason = ""
        trigger_mode = getattr(stream, 'trigger_mode', 'ANY_TARGET')

        # 1. Règle CRITIQUE : Personne avec objet sensible ou manipulation
        if person_count >= 1 and len(suspect_obj_boxes) > 0:
            if check_person_object_proximity(person_boxes, suspect_obj_boxes, PERSON_OBJ_MAX_DISTANCE_PX):
                is_alert = True
                severity = "CRITICAL"
                alert_reason = "PERSON_WITH_VALUABLE_OBJECT"

        # 2. Règle SUSPECT : Attroupement (>= 3 personnes)
        if not is_alert and person_count >= 3:
            is_alert = True
            severity = "SUSPICIOUS"
            alert_reason = "SUSPICIOUS_GROUP"

        # 3. Mode Détection Immédiate (ANY_TARGET) : Alerte dès qu'une cible sélectionnée apparaît
        if trigger_mode == "ANY_TARGET" and not is_alert:
            if person_count >= 1:
                is_alert = True
                severity = "SUSPICIOUS"
                alert_reason = "PERSON_DETECTED"
            elif len(suspect_obj_boxes) > 0:
                is_alert = True
                severity = "SUSPICIOUS"
                alert_reason = "SUSPECT_OBJECT_DETECTED"
            elif len(vehicle_boxes) > 0:
                is_alert = True
                severity = "INFO"
                alert_reason = "VEHICLE_DETECTED"
            elif len(detected_objs) > 0:
                is_alert = True
                severity = "INFO"
                alert_reason = f"TARGET_{detected_objs[0].upper()}"

        # 4. Mode FORENSIC Strict : Seuls véhicules, personnes+objets ou foules alertent
        elif trigger_mode == "FORENSIC" and not is_alert:
            if len(vehicle_boxes) > 0:
                is_alert = True
                severity = "INFO"
                alert_reason = "VEHICLE_DETECTED"

        # Gestion anti-flooding par caméra
        now = time.time()
        if is_alert:
            time_since_last = now - stream.last_alert_time
            is_same_type = (alert_reason == stream.last_alert_reason)

            if is_same_type and time_since_last < stream.cooldown_sec:
                is_alert = False
            else:
                stream.last_alert_time = now
                stream.last_alert_reason = alert_reason

        if is_alert:
            stream.total_events += 1
            self._save_live_event(
                stream=stream,
                frame=annotated_frame,
                detected_objs=detected_objs,
                person_count=person_count,
                max_conf=max_conf,
                severity=severity,
                track_id=primary_track_id
            )

    def _save_live_event(self, stream: RTSPStreamReader, frame, detected_objs,
                         person_count, max_conf, severity, track_id):
        """Enregistre un snapshot et insère l'événement dans evidence_db.sqlite."""
        now_dt = datetime.datetime.now()
        timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        file_ts = now_dt.strftime("%Y%m%d_%H%M%S_%f")[:19]

        snapshot_filename = f"live_{stream.camera_id}_{file_ts}.jpg"
        snapshots_dir = Path(OUTPUT_FOLDER) / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = str(snapshots_dir / snapshot_filename)

        # Sauvegarde disque de l'image annotée
        if cv2 is not None:
            cv2.imwrite(snapshot_path, frame)

        # Insertion en base SQLite
        try:
            conn = sqlite3.connect(DB_PATH, timeout=20.0)
            conn.execute('PRAGMA journal_mode=WAL;')
            cursor = conn.cursor()

            # Enregistrement ou mise à jour de la caméra dans la table videos
            video_ref_name = f"RTSP: [{stream.camera_id}] {stream.name}"
            cursor.execute("SELECT id FROM videos WHERE filename=?", (video_ref_name,))
            row = cursor.fetchone()

            if row:
                video_db_id = row[0]
                cursor.execute(
                    "UPDATE videos SET status='LIVE', processed_date=?, total_frames=?, fps=? WHERE id=?",
                    (now_dt, stream.total_frames_read, stream.fps_actual or 25.0, video_db_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO videos (filename, status, processed_date, total_frames, fps, sha256) "
                    "VALUES (?, 'LIVE', ?, ?, ?, 'FLUX_DIRECT_RTSP')",
                    (video_ref_name, now_dt, stream.total_frames_read, stream.fps_actual or 25.0)
                )
                video_db_id = cursor.lastrowid

            classes_str = ", ".join(sorted(list(set(detected_objs))))

            cursor.execute('''
                INSERT INTO events (
                    video_id, timestamp_str, frame_id, obj_class,
                    count_people, snapshot_path, confidence, is_suspicious,
                    severity, track_id, qualification, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'A_VERIFIER', '')
            ''', (
                video_db_id, timestamp_str, stream.total_frames_read, classes_str,
                person_count, snapshot_filename, max_conf, severity, track_id
            ))
            conn.commit()
            conn.close()

            logger.info(f"[ALERTE EN DIRECT] [{severity}] sur '{stream.name}' : {classes_str} (Personnes: {person_count})")

            # Notification Telegram si activée
            if TELEGRAM_ENABLED and severity in ("CRITICAL", "SUSPICIOUS"):
                self._dispatch_telegram(
                    camera_name=stream.name,
                    timestamp_str=timestamp_str,
                    severity=severity,
                    classes_str=classes_str,
                    person_count=person_count,
                    snapshot_filename=snapshot_filename
                )

        except Exception as e:
            logger.error(f"Erreur d'enregistrement d'evenement en base : {e}")

    def _dispatch_telegram(self, camera_name, timestamp_str, severity, classes_str, person_count, snapshot_filename):
        """Transmet une alerte photo vers Telegram."""
        if not TELEGRAM_BOT_TOKEN:
            return
        try:
            import urllib.request
            caption = (
                f"<b>Ocularis AI — Alerte En Direct {severity}</b>\n"
                f"<b>Camera :</b> <code>{camera_name}</code>\n"
                f"<b>Horodatage :</b> {timestamp_str}\n"
                f"<b>Personnes :</b> {person_count}\n"
                f"<b>Detections :</b> {classes_str}\n"
                f"<i>Ocularis AI Surveillance CCTV</i>"
            )
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            full_path = Path(OUTPUT_FOLDER) / "snapshots" / snapshot_filename
            if not full_path.exists():
                return

            with open(full_path, 'rb') as f:
                img_data = f.read()

            boundary = '----WebKitFormBoundaryOcularisLive'
            body = []
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{TELEGRAM_CHAT_ID}'.encode())
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}'.encode())
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="parse_mode"\r\n\r\nHTML'.encode())
            body.append(f'--{boundary}'.encode())
            body.append(f'Content-Disposition: form-data; name="photo"; filename="{snapshot_filename}"\r\nContent-Type: image/jpeg\r\n'.encode())
            body.append(img_data)
            body.append(f'--{boundary}--\r\n'.encode())

            data = b'\r\n'.join(body)
            req = urllib.request.Request(url, data=data)
            req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
            with urllib.request.urlopen(req, timeout=8) as response:
                pass
            logger.info(f"[TELEGRAM] Alerte en direct transmise pour '{camera_name}'")
        except Exception as e:
            logger.warning(f"Echec Telegram en direct : {e}")

    # --- GÉNÉRATEUR MJPEG POUR STREAMING WEB ---

    def generate_mjpeg_stream(self, cam_id: str, annotated: bool = True):
        """
        Générateur de flux vidéo MJPEG pour intégration dans Flask.
        Yields des paquets multipart/x-mixed-replace JPEG en temps réel.
        """
        stream = self.get_camera(cam_id)
        if not stream:
            placeholder = create_placeholder_frame("Caméra introuvable", f"Identifiant '{cam_id}' inconnu")
            if placeholder is not None and cv2 is not None:
                _, jpeg = cv2.imencode('.jpg', placeholder)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            return

        while True:
            frame = None
            if stream.enabled and stream.status == "LIVE":
                frame = stream.get_latest_frame(annotated=annotated)

            if frame is None:
                status_txt = "Caméra Désactivée" if not stream.enabled else f"Statut : {stream.status}"
                sub_txt = stream.error_message if stream.error_message else "En attente de connexion RTSP..."
                frame = create_placeholder_frame(f"{stream.name} - {status_txt}", sub_txt)

            if frame is not None and cv2 is not None:
                # Compression JPEG optimisée pour le web (qualité 75)
                ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

            time.sleep(0.04)  # ~25 FPS pour fluidité maximale sans surchauffe CPU
