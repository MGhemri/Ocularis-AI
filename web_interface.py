"""
OCULARIS AI - INTERFACE WEB FORENSIQUE & MONITORING RTSP (FRONTEND)
Version 1.2.0 - Grade Industriel - Dashboard Enquêteur, Flux En Direct & Rapports Officiels
Système Universel d'Analyse Forensique Vidéo & Audit CCTV
Développeur : Ghemri M (contact@connect-gm.com / +213 549 777 366)
"""

import os
import csv
import io
import sqlite3
import datetime
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, send_from_directory, Response

# Ingestion du gestionnaire RTSP multi-caméras
try:
    from rtsp_manager import MultiCameraRTSPManager, test_rtsp_connection
    rtsp_manager = MultiCameraRTSPManager.get_instance()
except Exception as e:
    print(f"[AVERTISSEMENT] Initialisation RTSP Manager en mode degrade : {e}")
    rtsp_manager = None

app = Flask(__name__)

# --- CONFIGURATION ---
OUTPUT_FOLDER = os.getenv("OCULARIS_OUTPUT_FOLDER", os.getenv("GM_OUTPUT_FOLDER", "./resultats_enquete"))
DB_PATH = f"{OUTPUT_FOLDER}/evidence_db.sqlite"


def get_db():
    """Connexion SQLite robuste en mode WAL et row_factory."""
    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db():
    """Assure que les tables existent pour éviter les erreurs HTTP 500 au premier démarrage."""
    Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)
    Path(f"{OUTPUT_FOLDER}/snapshots").mkdir(parents=True, exist_ok=True)
    conn = get_db()
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
    conn.close()


# --- TEMPLATE DASHBOARD ENQUÊTEUR OCULARIS AI V1.2.0 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ocularis AI — Système d'Analyse Forensique & Surveillance RTSP</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #0284c7; --primary-dark: #0369a1; --secondary: #3b82f6;
            --danger: #dc2626; --danger-bg: #fee2e2;
            --warning: #d97706; --warning-bg: #fef3c7;
            --success: #16a34a; --success-bg: #dcfce7;
            --dark: #0f172a; --slate: #1e293b; --light: #f8fafc; --border: #cbd5e1;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
            min-height: 100vh; padding: 20px; color: var(--dark);
        }
        .container { max-width: 1520px; margin: 0 auto; }
        
        /* Header */
        .header {
            background: white; border-radius: 14px; padding: 20px 28px; margin-bottom: 20px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.18); display: flex; justify-content: space-between;
            align-items: center; flex-wrap: wrap; gap: 16px;
        }
        .brand { display: flex; align-items: center; gap: 16px; }
        .logo {
            width: 52px; height: 52px; background: linear-gradient(135deg, #0284c7, #2563eb);
            border-radius: 12px; display: flex; align-items: center; justify-content: center;
            font-size: 24px; color: white; font-weight: 800; letter-spacing: -0.5px;
            box-shadow: 0 4px 14px rgba(2, 132, 199, 0.4);
        }
        .brand-text h1 { font-size: 22px; color: var(--dark); font-weight: 800; margin-bottom: 2px; }
        .brand-text p { font-size: 13px; color: #64748b; font-weight: 500; }
        
        .header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .btn {
            padding: 9px 16px; border-radius: 8px; font-size: 13px; font-weight: 600;
            border: none; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
            transition: all 0.2s ease; text-decoration: none;
        }
        .btn-primary { background: var(--primary); color: white; }
        .btn-primary:hover { background: var(--primary-dark); transform: translateY(-1px); }
        .btn-success { background: #16a34a; color: white; }
        .btn-success:hover { background: #15803d; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-danger:hover { background: #b91c1c; }
        .btn-outline { background: white; border: 1px solid var(--border); color: #334155; }
        .btn-outline:hover { background: #f1f5f9; }
        
        .status-live {
            display: flex; align-items: center; gap: 8px; background: #dcfce7;
            color: #166534; padding: 7px 14px; border-radius: 8px;
            font-weight: 700; font-size: 12px;
        }
        .status-dot {
            width: 8px; height: 8px; background: #16a34a;
            border-radius: 50%; animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.2); } }

        /* Navigation Tabs */
        .nav-tabs {
            display: flex; gap: 10px; margin-bottom: 22px; flex-wrap: wrap;
        }
        .nav-tab-btn {
            padding: 12px 22px; border-radius: 10px; font-size: 14px; font-weight: 700;
            border: none; cursor: pointer; background: rgba(255, 255, 255, 0.85); color: #334155;
            display: inline-flex; align-items: center; gap: 10px; transition: all 0.2s ease;
            box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        }
        .nav-tab-btn:hover { background: white; transform: translateY(-1px); }
        .nav-tab-btn.active {
            background: white; color: var(--primary); box-shadow: 0 6px 18px rgba(0,0,0,0.12);
            border-bottom: 3px solid var(--primary);
        }
        .tab-badge {
            background: #e0f2fe; color: #0284c7; padding: 3px 9px; border-radius: 12px;
            font-size: 11px; font-weight: 800;
        }
        .tab-badge.live { background: #dcfce7; color: #166534; }

        /* Stats Grid */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 22px; }
        .stat-card {
            background: white; border-radius: 12px; padding: 18px 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); }
        .stat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .stat-icon {
            width: 40px; height: 40px; border-radius: 10px; display: flex;
            align-items: center; justify-content: center; font-size: 18px;
        }
        .stat-icon.primary { background: #e0f2fe; color: #0284c7; }
        .stat-icon.danger { background: #fee2e2; color: #dc2626; }
        .stat-icon.warning { background: #fef3c7; color: #d97706; }
        .stat-icon.success { background: #dcfce7; color: #16a34a; }
        .stat-icon.purple { background: #f3e8ff; color: #7c3aed; }
        .stat-value { font-size: 26px; font-weight: 800; color: var(--dark); line-height: 1; }
        .stat-label { font-size: 12px; color: #64748b; margin-top: 6px; font-weight: 600; }

        /* Tab Content Containers */
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* Section RTSP Live Stream Wall */
        .cams-wall-header {
            background: white; border-radius: 12px; padding: 16px 22px; margin-bottom: 18px;
            display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06);
        }
        .cams-wall-title { font-size: 18px; font-weight: 800; color: var(--dark); display: flex; align-items: center; gap: 10px; }
        
        .cams-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
            gap: 20px;
        }
        .cam-card {
            background: white; border-radius: 14px; overflow: hidden;
            box-shadow: 0 8px 24px rgba(0,0,0,0.12); border: 1px solid #e2e8f0;
            display: flex; flex-direction: column;
        }
        .cam-card-header {
            padding: 12px 18px; background: #0f172a; color: white;
            display: flex; justify-content: space-between; align-items: center;
        }
        .cam-card-title { font-size: 14px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
        .cam-badge-status {
            padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase;
        }
        .cam-badge-status.LIVE { background: #16a34a; color: white; }
        .cam-badge-status.CONNECTING { background: #d97706; color: white; }
        .cam-badge-status.RECONNECTING { background: #d97706; color: white; }
        .cam-badge-status.STOPPED { background: #64748b; color: white; }
        .cam-badge-status.ERROR { background: #dc2626; color: white; }

        .cam-stream-wrap {
            position: relative; width: 100%; aspect-ratio: 16/9; background: #000;
            overflow: hidden; display: flex; align-items: center; justify-content: center;
        }
        .cam-stream-wrap img {
            width: 100%; height: 100%; object-fit: contain; display: block;
        }
        .cam-card-footer {
            padding: 12px 18px; background: #f8fafc; border-top: 1px solid #e2e8f0;
            display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;
        }
        .cam-metrics { font-size: 12px; color: #475569; font-weight: 600; display: flex; gap: 12px; }
        .cam-controls { display: flex; gap: 8px; align-items: center; }

        /* Configuration Caméras Table & Form */
        .config-container {
            background: white; border-radius: 14px; padding: 26px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1);
        }
        .config-form {
            background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 22px; margin-bottom: 28px;
        }
        .form-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 16px;
        }
        .form-group label {
            display: block; font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 6px; text-transform: uppercase;
        }
        .form-group input, .form-group select {
            width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px;
            font-size: 13px; background: white; color: #1e293b;
        }
        .form-group input:focus, .form-group select:focus { outline: none; border-color: var(--primary); }

        .table-responsive { overflow-x: auto; margin-top: 15px; }
        .data-table {
            width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;
        }
        .data-table th {
            background: #f1f5f9; padding: 12px 14px; font-weight: 700; color: #334155; border-bottom: 2px solid #e2e8f0;
        }
        .data-table td {
            padding: 12px 14px; border-bottom: 1px solid #e2e8f0; color: #1e293b; vertical-align: middle;
        }
        .data-table tr:hover { background: #f8fafc; }

        /* Filters Bar */
        .filters {
            background: white; border-radius: 12px; padding: 18px 22px; margin-bottom: 22px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06); display: flex; gap: 14px; flex-wrap: wrap; align-items: flex-end;
        }
        .filter-group { flex: 1; min-width: 160px; }
        .filter-group label { display: block; font-size: 11px; font-weight: 700; color: #475569; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .filter-group select {
            width: 100%; padding: 9px 12px; border: 1px solid var(--border);
            border-radius: 8px; font-size: 13px; background: white; color: #1e293b; font-weight: 500;
        }
        .filter-group select:focus { outline: none; border-color: var(--primary); }

        /* Events Section */
        .events-container { background: white; border-radius: 14px; padding: 26px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); }
        .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
        .section-title { font-size: 18px; font-weight: 800; color: var(--dark); display: flex; align-items: center; gap: 10px; }
        .section-count { font-size: 12px; color: #64748b; font-weight: 600; background: #f1f5f9; padding: 4px 12px; border-radius: 20px; }

        .events-grid { display: grid; gap: 18px; }
        .event-card {
            background: #f8fafc; border-radius: 12px; padding: 18px; display: grid;
            grid-template-columns: 290px 1fr; gap: 20px; border: 1px solid #e2e8f0; transition: all 0.2s;
        }
        .event-card:hover { box-shadow: 0 6px 18px rgba(0,0,0,0.08); border-color: #94a3b8; }
        .event-card.retained { border-left: 5px solid #16a34a; background: #f0fdf4; }
        .event-card.dismissed { opacity: 0.55; border-left: 5px solid #94a3b8; }

        .event-image { position: relative; border-radius: 8px; overflow: hidden; cursor: pointer; height: 185px; background: #000; }
        .event-image img { width: 100%; height: 100%; object-fit: contain; transition: transform 0.25s; }
        .event-image:hover img { transform: scale(1.04); }
        .zoom-icon {
            position: absolute; top: 8px; right: 8px; background: rgba(0,0,0,0.7);
            color: white; width: 32px; height: 32px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center; font-size: 14px; opacity: 0; transition: opacity 0.2s;
        }
        .event-image:hover .zoom-icon { opacity: 1; }

        .event-details { display: flex; flex-direction: column; gap: 10px; justify-content: space-between; }
        .event-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
        .event-title { font-size: 15px; font-weight: 700; color: #0f172a; word-break: break-all; }
        
        .event-meta { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .meta-tag { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; display: inline-flex; align-items: center; gap: 5px; }
        .meta-tag.time { background: #fef3c7; color: #b45309; }
        .meta-tag.people { background: #fee2e2; color: #b91c1c; }
        .meta-tag.conf { background: #e0f2fe; color: #0369a1; }
        .meta-tag.sev-crit { background: #dc2626; color: white; }
        .meta-tag.sev-susp { background: #d97706; color: white; }
        .meta-tag.sev-info { background: #0284c7; color: white; }

        .event-objects { background: white; padding: 10px 14px; border-radius: 8px; border: 1px solid #e2e8f0; }
        .objects-title { font-size: 11px; font-weight: 700; color: #64748b; margin-bottom: 6px; text-transform: uppercase; }
        .object-chips { display: flex; flex-wrap: wrap; gap: 6px; }
        .object-chip { background: #0369a1; color: white; padding: 3px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; }

        /* Actions qualification */
        .event-actions { display: flex; gap: 10px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
        .btn-qualif {
            padding: 5px 12px; font-size: 11px; font-weight: 700; border-radius: 6px;
            cursor: pointer; border: 1px solid transparent; transition: all 0.15s;
        }
        .btn-retain { background: #dcfce7; color: #166534; border-color: #86efac; }
        .btn-retain:hover { background: #bbf7d0; }
        .btn-dismiss { background: #f1f5f9; color: #64748b; border-color: #cbd5e1; }
        .btn-dismiss:hover { background: #e2e8f0; }
        .notes-preview { font-size: 12px; color: #475569; font-style: italic; margin-left: 6px; }

        /* Modal */
        .modal { display: none; position: fixed; z-index: 2000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(15, 23, 42, 0.94); justify-content: center; align-items: center; padding: 20px; }
        .modal.active { display: flex; }
        .modal-content { max-width: 92%; max-height: 92%; display: flex; flex-direction: column; align-items: center; }
        .modal-content img { width: auto; max-width: 100%; max-height: 82vh; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); object-fit: contain; }
        .modal-caption { margin-top: 14px; color: #cbd5e1; font-size: 14px; font-weight: 600; text-align: center; }
        .modal-close { position: absolute; top: 20px; right: 28px; color: white; font-size: 38px; font-weight: bold; cursor: pointer; }
        .modal-close:hover { color: #f87171; }

        @media (max-width: 920px) {
            .event-card { grid-template-columns: 1fr; }
            .cams-grid { grid-template-columns: 1fr; }
            .header { flex-direction: column; align-items: flex-start; }
            .filters { flex-direction: column; }
        }
        
        .footer { text-align: center; padding: 26px 15px; color: #94a3b8; font-size: 13px; font-weight: 500; }
        .footer a { color: #cbd5e1; text-decoration: none; border-bottom: 1px dotted #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <div class="brand">
                <div class="logo">OC</div>
                <div class="brand-text">
                    <h1>Ocularis AI</h1>
                    <p>Système Universel d'Analyse Forensique & Surveillance RTSP v1.2.0</p>
                </div>
            </div>
            <div class="header-actions">
                <div class="status-live">
                    <div class="status-dot"></div>
                    Moteur IA Actif
                </div>
                <a href="/report" target="_blank" class="btn btn-outline">Rapport d'Enquete</a>
                <a href="/api/export/csv" class="btn btn-outline">Export CSV</a>
                <button class="btn btn-primary" id="btn-refresh">Actualiser</button>
            </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="nav-tab-btn active" data-tab="tab-events">
                Evenements & Preuves Forensiques
                <span class="tab-badge" id="badge-events-count">0</span>
            </button>
            <button class="nav-tab-btn" data-tab="tab-live">
                Flux En Direct (RTSP)
                <span class="tab-badge live" id="badge-live-count">0 en direct</span>
            </button>
            <button class="nav-tab-btn" data-tab="tab-config">
                Configuration Cameras IP
            </button>
        </div>

        <!-- Stats Dashboard -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon primary" style="font-size:12px; font-weight:800;">SRC</div>
                </div>
                <div class="stat-value" id="stat-videos">0</div>
                <div class="stat-label">Sources & Cameras</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon danger" style="font-size:12px; font-weight:800;">CRI</div>
                </div>
                <div class="stat-value" id="stat-critical">0</div>
                <div class="stat-label">Alertes Critiques</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon warning" style="font-size:12px; font-weight:800;">EVT</div>
                </div>
                <div class="stat-value" id="stat-events">0</div>
                <div class="stat-label">Total Detections</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon success" style="font-size:12px; font-weight:800;">RET</div>
                </div>
                <div class="stat-value" id="stat-retained">0</div>
                <div class="stat-label">Preuves Retenues</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon purple" style="font-size:12px; font-weight:800;">CNF</div>
                </div>
                <div class="stat-value" id="stat-confidence">0%</div>
                <div class="stat-label">Confiance Moyenne</div>
            </div>
        </div>

        <!-- TAB 1 : ÉVÉNEMENTS FORENSIQUES -->
        <div id="tab-events" class="tab-content active">
            <!-- Filters -->
            <div class="filters">
                <div class="filter-group">
                    <label>Source / Camera</label>
                    <select id="filter-video"><option value="">Toutes les cameras</option></select>
                </div>
                <div class="filter-group">
                    <label>Severite</label>
                    <select id="filter-severity">
                        <option value="">Toutes les severites</option>
                        <option value="CRITICAL">Critique (Personne + Objet)</option>
                        <option value="SUSPICIOUS">Suspect (Attroupement)</option>
                        <option value="INFO">Information (Vehicule)</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Qualification Enqueteur</label>
                    <select id="filter-qualification">
                        <option value="">Toutes</option>
                        <option value="RETENU">Preuves Retenues</option>
                        <option value="A_VERIFIER" selected>A Verifier</option>
                        <option value="FAUX_POSITIF">Faux Positifs</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Type d'Objet</label>
                    <select id="filter-object">
                        <option value="">Tous les objets</option>
                        <option value="person">Personne</option>
                        <option value="suitcase">Valise</option>
                        <option value="backpack">Sac à dos</option>
                        <option value="handbag">Sac à main</option>
                        <option value="tv">Télévision / Écran</option>
                        <option value="laptop">PC Portable</option>
                        <option value="car">Voiture</option>
                        <option value="truck">Camion</option>
                        <option value="bus">Bus</option>
                    </select>
                </div>
                <div class="filter-group">
                    <label>Personnes</label>
                    <select id="filter-people">
                        <option value="">Tous</option>
                        <option value="1">1 personne</option>
                        <option value="2">2 personnes</option>
                        <option value="3+">3+ personnes (Groupe)</option>
                    </select>
                </div>
            </div>

            <!-- Events Container -->
            <div class="events-container">
                <div class="section-header">
                    <div class="section-title">
                        Evenements & Preuves Forensiques
                    </div>
                    <div class="section-count" id="events-count">0 événement(s) affiché(s)</div>
                </div>
                <div id="events-list" class="events-grid">
                    <div style="text-align:center; padding:50px; color:#64748b; font-weight:600;">Chargement des données...</div>
                </div>
            </div>
        </div>

        <!-- TAB 2 : FLUX CAMÉRAS EN DIRECT (RTSP) -->
        <div id="tab-live" class="tab-content">
            <div class="cams-wall-header">
                <div class="cams-wall-title">
                    Mur de Surveillance CCTV en Direct (Zero-Latence Bufferless)
                </div>
                <div>
                    <button class="btn btn-outline" id="btn-toggle-all-annot">Basculer Mode IA / Brut</button>
                    <button class="btn btn-primary" onclick="switchTab('tab-config')">Configurer Cameras</button>
                </div>
            </div>
            <div id="live-cams-container" class="cams-grid">
                <!-- Rempli dynamiquement en JS -->
            </div>
        </div>

        <!-- TAB 3 : CONFIGURATION DES CAMÉRAS -->
        <div id="tab-config" class="tab-content">
            <div class="config-container">
                <div class="section-header">
                    <div class="section-title">
                        Parametrage des Cameras IP & Flux RTSP
                    </div>
                </div>

                <!-- Formulaire d'ajout / modification -->
                <div class="config-form">
                    <h3 style="font-size:15px; margin-bottom:14px; color:#0f172a;">Ajouter ou Modifier une Caméra</h3>
                    <div class="form-grid">
                        <div class="form-group">
                            <label>ID Unique (ex: cam_01)</label>
                            <input type="text" id="cam-id" placeholder="cam_01" required>
                        </div>
                        <div class="form-group">
                            <label>Nom de la Caméra</label>
                            <input type="text" id="cam-name" placeholder="Entrée Principale" required>
                        </div>
                        <div class="form-group" style="grid-column: span 2;">
                            <label>URL du Flux RTSP / IP (ou '0' pour webcam locale)</label>
                            <input type="text" id="cam-url" placeholder="rtsp://admin:motdepasse@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0" required>
                        </div>
                    </div>

                    <!-- Presets rapides constructeurs -->
                    <div style="margin-bottom:16px; font-size:12px; color:#64748b; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                        <span style="font-weight:700;">Modèles prédéfinis :</span>
                        <button type="button" class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="applyPreset('dahua')">Dahua</button>
                        <button type="button" class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="applyPreset('hikvision')">Hikvision</button>
                        <button type="button" class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="applyPreset('uniview')">Uniview</button>
                        <button type="button" class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="applyPreset('axis')">Axis</button>
                        <button type="button" class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="applyPreset('webcam')">Webcam USB (0)</button>
                    </div>

                    <div class="form-grid">
                        <div class="form-group">
                            <label>Fréquence d'analyse IA (FPS)</label>
                            <input type="number" id="cam-fps" value="2.0" step="0.5" min="0.5" max="10.0">
                        </div>
                        <div class="form-group">
                            <label>Cooldown Anti-Flooding (sec)</label>
                            <input type="number" id="cam-cooldown" value="3.5" step="0.5" min="1.0">
                        </div>
                        <div class="form-group" style="display:flex; align-items:center; gap:10px; margin-top:22px;">
                            <input type="checkbox" id="cam-enabled" checked style="width:20px; height:20px;">
                            <label for="cam-enabled" style="margin:0; text-transform:none; font-size:13px; font-weight:600;">Activer le flux immédiatement</label>
                        </div>
                    </div>

                    <div style="display:flex; gap:12px; align-items:center; margin-top:14px; flex-wrap:wrap;">
                        <button type="button" class="btn btn-primary" id="btn-save-cam">Enregistrer la Camera</button>
                        <button type="button" class="btn btn-outline" id="btn-test-cam">Tester la Connexion</button>
                        <span id="test-status" style="font-size:12px; font-weight:700;"></span>
                    </div>
                </div>

                <!-- Table récapitulative des caméras -->
                <h3 style="font-size:15px; margin-bottom:12px; color:#0f172a;">Caméras Enregistrées dans cameras.json</h3>
                <div class="table-responsive">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Statut</th>
                                <th>ID</th>
                                <th>Nom</th>
                                <th>URL Stream</th>
                                <th>FPS Réel</th>
                                <th>Résolution</th>
                                <th>Événements</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="cameras-table-body">
                            <tr><td colspan="8" style="text-align:center;">Chargement des caméras...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            © 2026 Ocularis AI — Grade Industriel v1.2.0 | 
            Système Universel d'Analyse Forensique Vidéo & Surveillance RTSP | 
            <a href="mailto:contact@connect-gm.com">contact@connect-gm.com</a> | 
            <a href="tel:+213549777366">+213 549 777 366</a>
        </div>
    </div>

    <!-- Image Modal -->
    <div id="imageModal" class="modal">
        <span class="modal-close" id="modalClose">&times;</span>
        <div class="modal-content">
            <img id="modalImage" src="" alt="Preuve Forensique">
            <div class="modal-caption" id="modalCaption"></div>
        </div>
    </div>

    <script>
        let allEvents = [];
        let currentMaxId = 0;
        let globalAnnotatedMode = true;
        let configuredCameras = [];

        function escapeHtml(str) {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        // --- NAVIGATION TABS ---
        function switchTab(tabId) {
            document.querySelectorAll('.nav-tab-btn').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
            });
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.toggle('active', content.id === tabId);
            });
            if (tabId === 'tab-live') {
                renderLiveCameras();
            } else if (tabId === 'tab-config') {
                loadCameras();
            }
        }

        document.querySelectorAll('.nav-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.getAttribute('data-tab')));
        });

        // --- CHARGEMENT STATS & EVENEMENTS ---
        function loadStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stat-videos').textContent = data.total_videos || 0;
                    document.getElementById('stat-events').textContent = data.total_events || 0;
                    document.getElementById('stat-critical').textContent = data.critical_events || 0;
                    document.getElementById('stat-retained').textContent = data.retained_events || 0;
                    document.getElementById('stat-confidence').textContent = (data.avg_confidence || 0) + '%';
                    document.getElementById('badge-events-count').textContent = data.total_events || 0;
                })
                .catch(err => console.error("Erreur stats:", err));
        }

        function loadEvents() {
            fetch('/api/events')
                .then(r => r.json())
                .then(data => {
                    const newMax = data.max_id || 0;
                    if (newMax !== currentMaxId || data.events.length !== allEvents.length) {
                        currentMaxId = newMax;
                        allEvents = data.events || [];
                        populateFilters(data.videos || []);
                        applyFilters();
                    }
                })
                .catch(err => console.error("Erreur events:", err));
        }

        function populateFilters(videos) {
            const select = document.getElementById('filter-video');
            const currentVal = select.value;
            const existingOptions = Array.from(select.options).map(o => o.value);
            
            videos.forEach(v => {
                if (!existingOptions.includes(v)) {
                    const opt = document.createElement('option');
                    opt.value = v;
                    opt.textContent = v;
                    select.appendChild(opt);
                }
            });
            if (currentVal) select.value = currentVal;
        }

        function applyFilters() {
            const videoFilter = document.getElementById('filter-video').value;
            const severityFilter = document.getElementById('filter-severity').value;
            const qualifFilter = document.getElementById('filter-qualification').value;
            const objectFilter = document.getElementById('filter-object').value.toLowerCase();
            const peopleFilter = document.getElementById('filter-people').value;

            const filtered = allEvents.filter(e => {
                if (videoFilter && e.filename !== videoFilter) return false;
                if (severityFilter && e.severity !== severityFilter) return false;
                if (qualifFilter && e.qualification !== qualifFilter) return false;
                if (objectFilter && !e.obj_class.toLowerCase().includes(objectFilter)) return false;
                if (peopleFilter) {
                    if (peopleFilter === '1' && e.count_people !== 1) return false;
                    if (peopleFilter === '2' && e.count_people !== 2) return false;
                    if (peopleFilter === '3+' && e.count_people < 3) return false;
                }
                return true;
            });

            renderEvents(filtered);
        }

        function renderEvents(events) {
            const container = document.getElementById('events-list');
            document.getElementById('events-count').textContent = `${events.length} événement(s) affiché(s)`;

            if (events.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:50px; color:#64748b; font-weight:600;">Aucun événement ne correspond aux filtres sélectionnés.</div>';
                return;
            }

            container.innerHTML = events.map(e => {
                const isRetained = e.qualification === 'RETENU';
                const isDismissed = e.qualification === 'FAUX_POSITIF';
                let cardClass = 'event-card';
                if (isRetained) cardClass += ' retained';
                if (isDismissed) cardClass += ' dismissed';

                let sevTag = '<span class="meta-tag sev-susp">Suspect</span>';
                if (e.severity === 'CRITICAL') sevTag = '<span class="meta-tag sev-crit">Critique</span>';
                else if (e.severity === 'INFO') sevTag = '<span class="meta-tag sev-info">Information</span>';

                const objects = e.obj_class.split(',').map(o => o.trim()).filter(Boolean);
                const chips = objects.map(o => `<span class="object-chip">${escapeHtml(o)}</span>`).join('');

                const notesHtml = e.notes ? `<span class="notes-preview">Note : « ${escapeHtml(e.notes)} »</span>` : '';

                return `
                    <div class="${cardClass}" id="event-row-${e.id}">
                        <div class="event-image" data-action="zoom" data-snapshot="${escapeHtml(e.snapshot_path)}" data-caption="${escapeHtml(e.filename)} — ${escapeHtml(e.timestamp_str)}">
                            <img src="/snapshots/${escapeHtml(e.snapshot_path)}" alt="Capture forensique" loading="lazy">
                            <div class="zoom-icon">ZOOM</div>
                        </div>
                        <div class="event-details">
                            <div class="event-top">
                                <div>
                                    <div class="event-title">${escapeHtml(e.filename)}</div>
                                    <div class="event-meta" style="margin-top:6px;">
                                        ${sevTag}
                                        <span class="meta-tag time">${escapeHtml(e.timestamp_str)}</span>
                                        <span class="meta-tag people">${e.count_people} pers.</span>
                                        <span class="meta-tag conf">${e.confidence}%</span>
                                        ${e.track_id ? `<span class="meta-tag" style="background:#f1f5f9; color:#475569;">Track #${e.track_id}</span>` : ''}
                                    </div>
                                </div>
                            </div>

                            <div class="event-objects">
                                <div class="objects-title">Objets identifiés</div>
                                <div class="object-chips">${chips || '<em>Aucun</em>'}</div>
                            </div>

                            <div class="event-actions">
                                <button class="btn-qualif btn-retain" data-action="qualify" data-id="${e.id}" data-type="RETENU">
                                    ${isRetained ? 'Preuve Retenue' : 'Retenir Preuve'}
                                </button>
                                <button class="btn-qualif btn-dismiss" data-action="qualify" data-id="${e.id}" data-type="FAUX_POSITIF">
                                    Faux Positif
                                </button>
                                <button class="btn-qualif btn-dismiss" data-action="note" data-id="${e.id}">
                                    Ajouter Note
                                </button>
                                ${notesHtml}
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // --- GESTION DES CAMÉRAS IP & FLUX RTSP ---
        function loadCameras() {
            fetch('/api/cameras')
                .then(r => r.json())
                .then(data => {
                    configuredCameras = data.cameras || [];
                    renderCamerasTable();
                    renderLiveCameras();
                    updateLiveBadge();
                })
                .catch(err => console.error("Erreur cameras:", err));
        }

        function updateLiveBadge() {
            const liveCount = configuredCameras.filter(c => c.enabled && c.status === 'LIVE').length;
            document.getElementById('badge-live-count').textContent = `${liveCount} en direct`;
        }

        function renderCamerasTable() {
            const tbody = document.getElementById('cameras-table-body');
            if (!tbody) return;

            if (configuredCameras.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:20px;">Aucune caméra configurée.</td></tr>';
                return;
            }

            tbody.innerHTML = configuredCameras.map(c => `
                <tr>
                    <td><span class="cam-badge-status ${c.status}">${c.status}</span></td>
                    <td><strong>${escapeHtml(c.id)}</strong></td>
                    <td>${escapeHtml(c.name)}</td>
                    <td><code>${escapeHtml(c.url)}</code></td>
                    <td>${c.fps_actual} FPS</td>
                    <td>${escapeHtml(c.resolution)}</td>
                    <td>${c.total_events}</td>
                    <td>
                        <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="toggleCamera('${c.id}')">
                            ${c.enabled ? 'Pause' : 'Activer'}
                        </button>
                        <button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteCamera('${c.id}')">
                            Supprimer
                        </button>
                    </td>
                </tr>
            `).join('');
        }

        function renderLiveCameras() {
            const container = document.getElementById('live-cams-container');
            if (!container) return;

            if (configuredCameras.length === 0) {
                container.innerHTML = `
                    <div style="grid-column:1/-1; background:white; border-radius:12px; padding:40px; text-align:center; color:#64748b;">
                        <h3 style="font-size:17px; margin-bottom:8px; color:#1e293b;">Aucun flux RTSP configuré</h3>
                        <p style="margin-bottom:16px;">Ajoutez vos flux de caméras IP (Hikvision, Dahua, Uniview, Axis ou webcam USB) dans l'onglet Configuration.</p>
                        <button class="btn btn-primary" onclick="switchTab('tab-config')">Configurer une première caméra</button>
                    </div>
                `;
                return;
            }

            container.innerHTML = configuredCameras.map(c => {
                const streamUrl = `/api/stream/${c.id}?annotated=${globalAnnotatedMode ? 1 : 0}`;
                return `
                    <div class="cam-card">
                        <div class="cam-card-header">
                            <div class="cam-card-title">
                                <span class="status-dot" style="background:${c.status === 'LIVE' ? '#16a34a' : '#d97706'}"></span>
                                ${escapeHtml(c.name)} <span style="font-size:12px; opacity:0.8;">(${escapeHtml(c.id)})</span>
                            </div>
                            <span class="cam-badge-status ${c.status}">${c.status}</span>
                        </div>
                        <div class="cam-stream-wrap">
                            <img src="${streamUrl}" alt="${escapeHtml(c.name)}">
                        </div>
                        <div class="cam-card-footer">
                            <div class="cam-metrics">
                                <span>${c.fps_actual} FPS</span>
                                <span>${escapeHtml(c.resolution)}</span>
                                <span>${c.total_events} alertes</span>
                            </div>
                            <div class="cam-controls">
                                <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="toggleCamera('${c.id}')">
                                    ${c.enabled ? 'Désactiver' : 'Activer'}
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function toggleCamera(camId) {
            fetch(`/api/cameras/${camId}/toggle`, { method: 'POST' })
                .then(r => r.json())
                .then(() => loadCameras())
                .catch(err => alert("Erreur: " + err));
        }

        function deleteCamera(camId) {
            if (!confirm(`Confirmer la suppression de la caméra '${camId}' ?`)) return;
            fetch(`/api/cameras/${camId}`, { method: 'DELETE' })
                .then(r => r.json())
                .then(() => loadCameras())
                .catch(err => alert("Erreur: " + err));
        }

        function applyPreset(brand) {
            const urlInput = document.getElementById('cam-url');
            if (brand === 'dahua') {
                urlInput.value = "rtsp://admin:admin123@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0";
            } else if (brand === 'hikvision') {
                urlInput.value = "rtsp://admin:admin123@192.168.1.100:554/Streaming/Channels/101";
            } else if (brand === 'uniview') {
                urlInput.value = "rtsp://admin:admin123@192.168.1.100:554/unicast/c1/s0/live";
            } else if (brand === 'axis') {
                urlInput.value = "rtsp://root:admin123@192.168.1.100:554/axis-media/media.amp";
            } else if (brand === 'webcam') {
                urlInput.value = "0";
            }
        }

        // Test de connexion RTSP
        document.getElementById('btn-test-cam')?.addEventListener('click', () => {
            const url = document.getElementById('cam-url').value.trim();
            const statusSpan = document.getElementById('test-status');
            if (!url) {
                alert("Veuillez saisir une URL RTSP valide.");
                return;
            }
            statusSpan.style.color = '#0284c7';
            statusSpan.textContent = "Test de connexion en cours (3.5s max)...";

            fetch('/api/cameras/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    statusSpan.style.color = '#16a34a';
                    statusSpan.textContent = `[OK] Connexion reussie ! Resolution : ${res.width}x${res.height} @ ${res.fps} FPS`;
                } else {
                    statusSpan.style.color = '#dc2626';
                    statusSpan.textContent = `[ECHEC] Connexion : ${res.error || 'Delai depasse'}`;
                }
            })
            .catch(err => {
                statusSpan.style.color = '#dc2626';
                statusSpan.textContent = "[ERREUR] Erreur reseau lors du test.";
            });
        });

        // Enregistrement d'une caméra
        document.getElementById('btn-save-cam')?.addEventListener('click', () => {
            const camId = document.getElementById('cam-id').value.trim();
            const camName = document.getElementById('cam-name').value.trim();
            const camUrl = document.getElementById('cam-url').value.trim();
            const camFps = parseFloat(document.getElementById('cam-fps').value) || 2.0;
            const camCooldown = parseFloat(document.getElementById('cam-cooldown').value) || 3.5;
            const camEnabled = document.getElementById('cam-enabled').checked;

            if (!camId || !camName || !camUrl) {
                alert("L'ID, le nom et l'URL sont obligatoires.");
                return;
            }

            fetch('/api/cameras', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: camId,
                    name: camName,
                    url: camUrl,
                    fps_analyze: camFps,
                    cooldown_sec: camCooldown,
                    enabled: camEnabled
                })
            })
            .then(r => r.json())
            .then(res => {
                if (res.error) {
                    alert("Erreur: " + res.error);
                } else {
                    alert("[OK] Camera enregistree avec succes !");
                    loadCameras();
                }
            })
            .catch(err => alert("Erreur d'enregistrement : " + err));
        });

        // Bascule Mode IA / Mode Brut
        document.getElementById('btn-toggle-all-annot')?.addEventListener('click', () => {
            globalAnnotatedMode = !globalAnnotatedMode;
            renderLiveCameras();
        });

        // --- GESTION DU MODAL IMAGE & QUALIFICATION ---
        const modal = document.getElementById('imageModal');
        const modalImg = document.getElementById('modalImage');
        const modalCaption = document.getElementById('modalCaption');
        const modalClose = document.getElementById('modalClose');

        function openModal(src, caption) {
            modalImg.src = src;
            modalCaption.textContent = caption;
            modal.classList.add('active');
        }

        modalClose.onclick = () => modal.classList.remove('active');
        modal.onclick = (e) => { if (e.target === modal) modal.classList.remove('active'); };

        // Délégation d'événements pour le zoom et la qualification
        document.getElementById('events-list').addEventListener('click', (e) => {
            const zoomTrigger = e.target.closest('[data-action="zoom"]');
            if (zoomTrigger) {
                const snap = zoomTrigger.getAttribute('data-snapshot');
                const caption = zoomTrigger.getAttribute('data-caption');
                openModal(`/snapshots/${snap}`, caption);
                return;
            }

            const qualifBtn = e.target.closest('[data-action="qualify"]');
            if (qualifBtn) {
                const eventId = qualifBtn.getAttribute('data-id');
                const qualifType = qualifBtn.getAttribute('data-type');
                fetch(`/api/events/${eventId}/qualify`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ qualification: qualifType })
                })
                .then(r => r.json())
                .then(() => {
                    const evt = allEvents.find(x => x.id === parseInt(eventId));
                    if (evt) evt.qualification = qualifType;
                    applyFilters();
                    loadStats();
                });
                return;
            }

            const noteBtn = e.target.closest('[data-action="note"]');
            if (noteBtn) {
                const eventId = noteBtn.getAttribute('data-id');
                const evt = allEvents.find(x => x.id === parseInt(eventId));
                const currentNote = evt ? evt.notes : '';
                const newNote = prompt("Saisissez votre note d'enquête forensique :", currentNote);
                if (newNote !== null) {
                    fetch(`/api/events/${eventId}/qualify`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ notes: newNote })
                    })
                    .then(r => r.json())
                    .then(() => {
                        if (evt) evt.notes = newNote;
                        applyFilters();
                    });
                }
            }
        });

        // Filtres dynamiques
        ['filter-video', 'filter-severity', 'filter-qualification', 'filter-object', 'filter-people'].forEach(id => {
            document.getElementById(id).addEventListener('change', applyFilters);
        });

        document.getElementById('btn-refresh').addEventListener('click', () => {
            loadStats();
            loadEvents();
            loadCameras();
        });

        // Chargement initial et rafraîchissement périodique
        loadStats();
        loadEvents();
        loadCameras();
        setInterval(loadStats, 5000);
        setInterval(loadEvents, 3000);
        setInterval(loadCameras, 8000);
    </script>
</body>
</html>
"""

# --- TEMPLATE DU RAPPORT OFFICIEL FORENSIQUE ---
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Rapport d'Enquête Forensique — Ocularis AI</title>
    <style>
        body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1e293b; padding: 40px; background: #fff; line-height: 1.5; }
        .report-header { border-bottom: 3px solid #0284c7; padding-bottom: 20px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: flex-end; }
        .brand-title { font-size: 26px; font-weight: 800; color: #0f172a; }
        .subtitle { font-size: 13px; color: #64748b; margin-top: 4px; }
        .meta-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 25px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }
        .meta-item strong { display: block; font-size: 11px; text-transform: uppercase; color: #64748b; }
        .meta-item span { font-size: 18px; font-weight: 700; color: #0284c7; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
        th { background: #0f172a; color: white; padding: 10px; text-align: left; }
        td { padding: 9px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
        tr:nth-child(even) { background: #f8fafc; }
        .snap-thumb { width: 85px; height: 50px; object-fit: contain; background: #000; border-radius: 4px; }
        .badge { padding: 3px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; display: inline-block; }
        .badge-crit { background: #dc2626; color: white; }
        .badge-susp { background: #d97706; color: white; }
        .badge-info { background: #0284c7; color: white; }
        .print-btn { background: #0284c7; color: white; padding: 10px 18px; border-radius: 6px; font-weight: bold; border: none; cursor: pointer; float: right; margin-bottom: 20px; }
        @media print { .print-btn { display: none; } body { padding: 0; } }
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()">Imprimer / Exporter en PDF</button>
    <div class="report-header">
        <div>
            <div class="brand-title">OCULARIS AI — RAPPORT FORENSIQUE VIDÉO</div>
            <div class="subtitle">Système Universel d'Analyse Forensique Vidéo & Audit CCTV</div>
        </div>
        <div style="text-align: right; font-size: 12px; color: #64748b;">
            Édité le : <strong>{{ now }}</strong><br>
            Développeur : <strong>Ghemri M</strong>
        </div>
    </div>

    <div class="meta-box">
        <div class="meta-item"><strong>Sources Analysées</strong><span>{{ total_videos }}</span></div>
        <div class="meta-item"><strong>Total Détections</strong><span>{{ total_events }}</span></div>
        <div class="meta-item"><strong>Preuves Retenues</strong><span>{{ retained_count }}</span></div>
        <div class="meta-item"><strong>Alertes Critiques</strong><span>{{ critical_count }}</span></div>
    </div>

    <h3>Registre des Événements & Preuves Forensiques</h3>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Aperçu</th>
                <th>Source / Caméra</th>
                <th>Horodatage</th>
                <th>Sévérité</th>
                <th>Objets & Détections</th>
                <th>Confiance</th>
                <th>Qualification & Notes</th>
            </tr>
        </thead>
        <tbody>
            {% for e in events %}
            <tr>
                <td><strong>#{{ e.id }}</strong></td>
                <td><img class="snap-thumb" src="/snapshots/{{ e.snapshot_path }}" alt="Snap"></td>
                <td><strong>{{ e.filename }}</strong></td>
                <td>{{ e.timestamp_str }}</td>
                <td>
                    {% if e.severity == 'CRITICAL' %}
                        <span class="badge badge-crit">CRITIQUE</span>
                    {% elif e.severity == 'SUSPICIOUS' %}
                        <span class="badge badge-susp">SUSPECT</span>
                    {% else %}
                        <span class="badge badge-info">INFO</span>
                    {% endif %}
                </td>
                <td>{{ e.obj_class }} ({{ e.count_people }} pers.)</td>
                <td>{{ e.confidence }}%</td>
                <td>
                    <strong>{{ e.qualification }}</strong><br>
                    <span style="color:#64748b; font-style:italic;">{{ e.notes or 'Aucune annotation' }}</span>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div style="margin-top: 40px; border-top: 1px solid #cbd5e1; padding-top: 15px; font-size: 11px; color: #94a3b8; display: flex; justify-content: space-between;">
        <span>Ocularis AI v1.2.0 — Rapport d'Enquête Officiel</span>
        <span>Contact : contact@connect-gm.com / +213 549 777 366</span>
    </div>
</body>
</html>
"""


@app.route('/')
def index():
    ensure_db()
    return render_template_string(HTML_TEMPLATE)


@app.route('/report')
def report():
    """Génère le rapport officiel imprimable en PDF pour les enquêteurs."""
    ensure_db()
    conn = get_db()
    cursor = conn.cursor()

    total_videos = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0] or 0
    total_events = cursor.execute("SELECT COUNT(*) FROM events").fetchone()[0] or 0
    retained_count = cursor.execute("SELECT COUNT(*) FROM events WHERE qualification='RETENU'").fetchone()[0] or 0
    critical_count = cursor.execute("SELECT COUNT(*) FROM events WHERE severity='CRITICAL'").fetchone()[0] or 0

    cursor.execute('''
        SELECT e.id, v.filename, e.timestamp_str, e.frame_id, e.obj_class, e.count_people,
               e.snapshot_path, e.confidence, e.severity, e.qualification, e.notes
        FROM events e
        JOIN videos v ON e.video_id = v.id
        WHERE e.qualification = 'RETENU' OR e.severity = 'CRITICAL'
        ORDER BY e.id DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append({
            'id': r['id'],
            'filename': r['filename'],
            'timestamp_str': r['timestamp_str'],
            'frame_id': r['frame_id'],
            'obj_class': r['obj_class'],
            'count_people': r['count_people'],
            'snapshot_path': r['snapshot_path'],
            'confidence': round(r['confidence'] * 100, 1) if r['confidence'] else 0,
            'severity': r['severity'] or 'SUSPICIOUS',
            'qualification': r['qualification'] or 'A_VERIFIER',
            'notes': r['notes'] or ''
        })

    now_str = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")

    return render_template_string(
        REPORT_TEMPLATE,
        now=now_str,
        total_videos=total_videos,
        total_events=total_events,
        retained_count=retained_count,
        critical_count=critical_count,
        events=events
    )


@app.route('/api/stats')
def get_stats():
    ensure_db()
    try:
        conn = get_db()
        cursor = conn.cursor()

        total_videos = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0] or 0
        total_events = cursor.execute("SELECT COUNT(*) FROM events").fetchone()[0] or 0
        total_people = cursor.execute("SELECT SUM(count_people) FROM events").fetchone()[0] or 0
        avg_conf = cursor.execute("SELECT AVG(confidence) FROM events").fetchone()[0] or 0
        critical_events = cursor.execute("SELECT COUNT(*) FROM events WHERE severity='CRITICAL'").fetchone()[0] or 0
        retained_events = cursor.execute("SELECT COUNT(*) FROM events WHERE qualification='RETENU'").fetchone()[0] or 0

        conn.close()
        return jsonify({
            'total_videos': total_videos,
            'total_events': total_events,
            'total_people': total_people,
            'avg_confidence': round(avg_conf * 100, 1),
            'critical_events': critical_events,
            'retained_events': retained_events
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/events')
def get_events():
    ensure_db()
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT e.id, v.filename, e.timestamp_str, e.frame_id, e.obj_class, 
                   e.count_people, e.snapshot_path, e.confidence, e.severity,
                   e.track_id, e.qualification, e.notes
            FROM events e 
            JOIN videos v ON e.video_id = v.id 
            ORDER BY e.id DESC LIMIT 500
        ''')
        rows = cursor.fetchall()

        cursor.execute("SELECT DISTINCT filename FROM videos ORDER BY filename")
        videos = [row[0] for row in cursor.fetchall()]

        max_id = cursor.execute("SELECT MAX(id) FROM events").fetchone()[0] or 0
        conn.close()

        events = []
        for row in rows:
            events.append({
                'id': row['id'],
                'filename': row['filename'],
                'timestamp_str': row['timestamp_str'],
                'frame_id': row['frame_id'],
                'obj_class': row['obj_class'],
                'count_people': row['count_people'],
                'snapshot_path': row['snapshot_path'],
                'confidence': round(row['confidence'] * 100, 1) if row['confidence'] else 0,
                'severity': row['severity'] or 'SUSPICIOUS',
                'track_id': row['track_id'],
                'qualification': row['qualification'] or 'A_VERIFIER',
                'notes': row['notes'] or ''
            })

        return jsonify({'events': events, 'videos': videos, 'max_id': max_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/events/<int:event_id>/qualify', methods=['POST'])
def qualify_event(event_id):
    """Enregistre la décision de l'enquêteur (RETENU, FAUX_POSITIF) et les notes associées."""
    ensure_db()
    data = request.get_json() or {}
    qualification = data.get('qualification')
    notes = data.get('notes')

    conn = get_db()
    cursor = conn.cursor()

    if qualification and notes is not None:
        cursor.execute("UPDATE events SET qualification=?, notes=? WHERE id=?", (qualification, notes, event_id))
    elif qualification:
        cursor.execute("UPDATE events SET qualification=? WHERE id=?", (qualification, event_id))
    elif notes is not None:
        cursor.execute("UPDATE events SET notes=? WHERE id=?", (notes, event_id))

    conn.commit()
    conn.close()

    return jsonify({
        'ok': True,
        'id': event_id,
        'qualification': qualification,
        'notes': notes
    })


@app.route('/api/export/csv')
def export_csv():
    """Génère et télécharge le journal forensique complet au format CSV standard RFC-4180."""
    ensure_db()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT e.id, v.filename, e.timestamp_str, e.frame_id, e.severity, e.qualification,
               e.count_people, e.obj_class, e.confidence, e.snapshot_path, e.notes, v.sha256
        FROM events e
        JOIN videos v ON e.video_id = v.id
        ORDER BY e.id ASC
    ''')
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        'ID_Evenement', 'Camera_Fichier', 'Horodatage', 'Frame_ID', 'Severite',
        'Qualification', 'Nombre_Personnes', 'Classes_Detectees', 'Confiance_Pourcent',
        'Fichier_Snapshot', 'Notes_Enqueteur', 'SHA256_Fichier_Video'
    ])

    for r in rows:
        conf_pct = round(r['confidence'] * 100, 1) if r['confidence'] else 0
        writer.writerow([
            r['id'], r['filename'], r['timestamp_str'], r['frame_id'],
            r['severity'] or 'SUSPICIOUS', r['qualification'] or 'A_VERIFIER',
            r['count_people'], r['obj_class'], f"{conf_pct}%",
            r['snapshot_path'], r['notes'] or '', r['sha256'] or ''
        ])

    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=journal_forensique_ocularis.csv"}
    )


@app.route('/snapshots/<path:filename>')
def serve_snapshot(filename):
    return send_from_directory(f"{OUTPUT_FOLDER}/snapshots", filename)


# --- ENDPOINTS API GESTION & STREAMING RTSP ---

@app.route('/api/cameras', methods=['GET', 'POST'])
def handle_cameras():
    """Liste ou ajoute/modifie les caméras configurées."""
    if rtsp_manager is None:
        return jsonify({'error': "Gestionnaire RTSP non disponible."}), 503

    if request.method == 'POST':
        data = request.get_json() or {}
        try:
            stream = rtsp_manager.add_or_update_camera(data)
            return jsonify({'ok': True, 'camera': stream.to_dict(mask_secret=True)})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    else:
        cameras = rtsp_manager.get_cameras_list(mask_secret=True)
        return jsonify({'cameras': cameras})


@app.route('/api/cameras/<camera_id>/toggle', methods=['POST'])
def toggle_camera_route(camera_id):
    """Active ou met en pause une caméra."""
    if rtsp_manager is None:
        return jsonify({'error': "Gestionnaire RTSP non disponible."}), 503

    data = request.get_json() or {}
    enabled = data.get('enabled')
    res = rtsp_manager.toggle_camera(camera_id, enabled)
    return jsonify({'ok': True, 'id': camera_id, 'enabled': res})


@app.route('/api/cameras/<camera_id>', methods=['DELETE'])
def delete_camera_route(camera_id):
    """Supprime une caméra de la configuration."""
    if rtsp_manager is None:
        return jsonify({'error': "Gestionnaire RTSP non disponible."}), 503

    res = rtsp_manager.delete_camera(camera_id)
    return jsonify({'ok': res, 'id': camera_id})


@app.route('/api/cameras/test', methods=['POST'])
def test_camera_route():
    """Teste la connectivité d'un flux RTSP / IP à la demande."""
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'error': "L'URL est requise."}), 400

    res = test_rtsp_connection(url)
    return jsonify(res)


@app.route('/api/stream/<camera_id>')
def stream_camera(camera_id):
    """Diffuse le flux vidéo MJPEG en direct pour une caméra donnée."""
    if rtsp_manager is None:
        return "Gestionnaire RTSP non disponible", 503

    annotated = request.args.get('annotated', '1') in ('1', 'true', 'True')
    return Response(
        rtsp_manager.generate_mjpeg_stream(camera_id, annotated=annotated),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


if __name__ == '__main__':
    ensure_db()
    host = os.getenv("OCULARIS_WEB_HOST", os.getenv("GM_WEB_HOST", "0.0.0.0"))
    port = int(os.getenv("OCULARIS_WEB_PORT", os.getenv("GM_WEB_PORT", "5000")))
    debug_mode = os.getenv("OCULARIS_WEB_DEBUG", os.getenv("GM_WEB_DEBUG", "0")) in ("1", "true", "True")

    print("=" * 66)
    print("[OCULARIS AI] Interface Web Forensique & RTSP v1.2.0")
    print("   Systeme Universel d'Analyse Forensique Video & Audit CCTV")
    print("=" * 66)
    print(f"Serveur actif sur  : http://localhost:{port}")
    print(f"Mur Cameras RTSP   : http://localhost:{port} (Onglet Flux En Direct)")
    print(f"Rapport d'enquete  : http://localhost:{port}/report")
    print(f"Export CSV         : http://localhost:{port}/api/export/csv")
    print("=" * 66)

    app.run(debug=debug_mode, host=host, port=port)
