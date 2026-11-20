"""
OCULARIS AI - INTERFACE WEB FORENSIQUE (FRONTEND)
Version 1.1.0 - Grade Industriel - Dashboard Enquêteur & Rapports Officiels
Système Universel d'Analyse Forensique Vidéo & Audit CCTV
Auteur : Ghemri M (contact@connect-gm.com / +213 549 777 366)
"""

import os
import csv
import io
import sqlite3
from pathlib import Path
from flask import Flask, render_template_string, jsonify, request, send_from_directory, Response

app = Flask(__name__)

# --- CONFIGURATION ---
OUTPUT_FOLDER = os.getenv("GM_OUTPUT_FOLDER", "./resultats_enquete")
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
    conn.commit()
    conn.close()


# --- TEMPLATE DASHBOARD ENQUÊTEUR OCULARIS AI V1.1.0 ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ocularis AI — Système d'Analyse Vidéo Forensique</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #0056b3; --primary-dark: #003d82; --secondary: #00a3e0;
            --danger: #dc3545; --danger-bg: #ffebee;
            --warning: #f57c00; --warning-bg: #fff3e0;
            --success: #28a745; --success-bg: #e8f5e9;
            --dark: #1e293b; --light: #f8fafc; --border: #cbd5e1;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #1e3a8a 0%, #312e81 100%);
            min-height: 100vh; padding: 20px; color: var(--dark);
        }
        .container { max-width: 1440px; margin: 0 auto; }
        
        /* Header */
        .header {
            background: white; border-radius: 14px; padding: 22px 28px; margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(0,0,0,0.15); display: flex; justify-content: space-between;
            align-items: center; flex-wrap: wrap; gap: 18px;
        }
        .brand { display: flex; align-items: center; gap: 16px; }
        .logo {
            width: 52px; height: 52px; background: linear-gradient(135deg, #0284c7, #3b82f6);
            border-radius: 12px; display: flex; align-items: center; justify-content: center;
            font-size: 24px; color: white; font-weight: 800; letter-spacing: -0.5px;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.35);
        }
        .brand-text h1 { font-size: 22px; color: var(--dark); font-weight: 800; margin-bottom: 2px; }
        .brand-text p { font-size: 13px; color: #64748b; font-weight: 500; }
        
        .header-actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
        .btn {
            padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;
            border: none; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
            transition: all 0.2s ease; text-decoration: none;
        }
        .btn-primary { background: var(--primary); color: white; }
        .btn-primary:hover { background: var(--primary-dark); transform: translateY(-1px); }
        .btn-success { background: #16a34a; color: white; }
        .btn-success:hover { background: #15803d; }
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

        /* Stats Grid */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 18px; margin-bottom: 24px; }
        .stat-card {
            background: white; border-radius: 12px; padding: 20px 22px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s;
        }
        .stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); }
        .stat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .stat-icon {
            width: 42px; height: 42px; border-radius: 10px; display: flex;
            align-items: center; justify-content: center; font-size: 20px;
        }
        .stat-icon.primary { background: #e0f2fe; color: #0284c7; }
        .stat-icon.danger { background: #fee2e2; color: #dc2626; }
        .stat-icon.warning { background: #fef3c7; color: #d97706; }
        .stat-icon.success { background: #dcfce7; color: #16a34a; }
        .stat-icon.purple { background: #f3e8ff; color: #7c3aed; }
        .stat-value { font-size: 28px; font-weight: 800; color: var(--dark); line-height: 1; }
        .stat-label { font-size: 13px; color: #64748b; margin-top: 8px; font-weight: 600; }

        /* Filters */
        .filters {
            background: white; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.06); display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-end;
        }
        .filter-group { flex: 1; min-width: 170px; }
        .filter-group label { display: block; font-size: 12px; font-weight: 700; color: #475569; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .filter-group select {
            width: 100%; padding: 9px 12px; border: 1px solid var(--border);
            border-radius: 8px; font-size: 13px; background: white; color: #1e293b; font-weight: 500;
        }
        .filter-group select:focus { outline: none; border-color: var(--primary); }

        /* Events Section */
        .events-container { background: white; border-radius: 14px; padding: 26px; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); }
        .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
        .section-title { font-size: 19px; font-weight: 800; color: var(--dark); display: flex; align-items: center; gap: 10px; }
        .section-count { font-size: 13px; color: #64748b; font-weight: 600; background: #f1f5f9; padding: 4px 12px; border-radius: 20px; }

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
        .event-title { font-size: 16px; font-weight: 700; color: #0f172a; word-break: break-all; }
        
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
        .modal { display: none; position: fixed; z-index: 2000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(15, 23, 42, 0.92); justify-content: center; align-items: center; padding: 20px; }
        .modal.active { display: flex; }
        .modal-content { max-width: 92%; max-height: 92%; display: flex; flex-direction: column; align-items: center; }
        .modal-content img { width: auto; max-width: 100%; max-height: 82vh; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); object-fit: contain; }
        .modal-caption { margin-top: 14px; color: #cbd5e1; font-size: 14px; font-weight: 600; text-align: center; }
        .modal-close { position: absolute; top: 20px; right: 28px; color: white; font-size: 38px; font-weight: bold; cursor: pointer; }
        .modal-close:hover { color: #f87171; }

        @media (max-width: 820px) {
            .event-card { grid-template-columns: 1fr; }
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
                    <p>Système Universel d'Analyse Forensique & Audit Vidéo v1.1.0</p>
                </div>
            </div>
            <div class="header-actions">
                <div class="status-live">
                    <div class="status-dot"></div>
                    Moteur Actif
                </div>
                <a href="/report" target="_blank" class="btn btn-outline">📄 Rapport d'Enquête</a>
                <a href="/api/export/csv" class="btn btn-outline">📥 Export CSV</a>
                <button class="btn btn-primary" id="btn-refresh">🔄 Actualiser</button>
            </div>
        </div>

        <!-- Stats Dashboard -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon primary">📹</div>
                </div>
                <div class="stat-value" id="stat-videos">0</div>
                <div class="stat-label">Caméras / Vidéos</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon danger">🚨</div>
                </div>
                <div class="stat-value" id="stat-critical">0</div>
                <div class="stat-label">Alertes Critiques</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon warning">⚠️</div>
                </div>
                <div class="stat-value" id="stat-events">0</div>
                <div class="stat-label">Total Événements</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon success">⭐</div>
                </div>
                <div class="stat-value" id="stat-retained">0</div>
                <div class="stat-label">Preuves Retenues</div>
            </div>
            <div class="stat-card">
                <div class="stat-header">
                    <div class="stat-icon purple">🎯</div>
                </div>
                <div class="stat-value" id="stat-confidence">0%</div>
                <div class="stat-label">Confiance Moyenne</div>
            </div>
        </div>

        <!-- Filters -->
        <div class="filters">
            <div class="filter-group">
                <label>Caméra / Fichier</label>
                <select id="filter-video"><option value="">Toutes les caméras</option></select>
            </div>
            <div class="filter-group">
                <label>Sévérité</label>
                <select id="filter-severity">
                    <option value="">Toutes les sévérités</option>
                    <option value="CRITICAL">🔴 Critique (Personne + Objet)</option>
                    <option value="SUSPICIOUS">🟠 Suspect (Attroupement)</option>
                    <option value="INFO">🔵 Information (Véhicule)</option>
                </select>
            </div>
            <div class="filter-group">
                <label>Qualification Enquêteur</label>
                <select id="filter-qualification">
                    <option value="">Toutes</option>
                    <option value="RETENU">⭐ Preuves Retenues</option>
                    <option value="A_VERIFIER" selected>⚠️ À Vérifier</option>
                    <option value="FAUX_POSITIF">🗑️ Faux Positifs</option>
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
                    🎯 Événements & Preuves Forensiques
                </div>
                <div class="section-count" id="events-count">0 événement(s) affiché(s)</div>
            </div>
            <div id="events-list" class="events-grid">
                <div style="text-align:center; padding:50px; color:#64748b; font-weight:600;">Chargement des données...</div>
            </div>
        </div>

        <!-- Footer -->
        <div class="footer">
            © 2026 Ocularis AI — Grade Industriel v1.1.0 | 
            Système Universel d'Analyse Forensique Vidéo | 
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

        function escapeHtml(str) {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        function loadStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stat-videos').textContent = data.total_videos || 0;
                    document.getElementById('stat-events').textContent = data.total_events || 0;
                    document.getElementById('stat-critical').textContent = data.critical_events || 0;
                    document.getElementById('stat-retained').textContent = data.retained_events || 0;
                    document.getElementById('stat-confidence').textContent = (data.avg_confidence || 0) + '%';
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
            const vidFilter = document.getElementById('filter-video').value;
            const sevFilter = document.getElementById('filter-severity').value;
            const qualFilter = document.getElementById('filter-qualification').value;
            const objFilter = document.getElementById('filter-object').value.toLowerCase();
            const pplFilter = document.getElementById('filter-people').value;

            let filtered = allEvents;

            if (vidFilter) filtered = filtered.filter(e => e.filename === vidFilter);
            if (sevFilter) filtered = filtered.filter(e => (e.severity || 'SUSPICIOUS') === sevFilter);
            if (qualFilter) filtered = filtered.filter(e => (e.qualification || 'A_VERIFIER') === qualFilter);
            if (objFilter) filtered = filtered.filter(e => (e.obj_class || '').toLowerCase().includes(objFilter));
            if (pplFilter) {
                if (pplFilter === '3+') filtered = filtered.filter(e => e.count_people >= 3);
                else filtered = filtered.filter(e => String(e.count_people) === pplFilter);
            }

            document.getElementById('events-count').textContent = `${filtered.length} événement(s) affiché(s)`;

            const container = document.getElementById('events-list');
            if (filtered.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:40px; color:#64748b; font-weight:600;">Aucun événement ne correspond aux filtres sélectionnés.</div>';
                return;
            }

            container.innerHTML = filtered.map(e => {
                const sevClass = e.severity === 'CRITICAL' ? 'sev-crit' : (e.severity === 'INFO' ? 'sev-info' : 'sev-susp');
                const sevLabel = e.severity === 'CRITICAL' ? '🔴 CRITIQUE' : (e.severity === 'INFO' ? '🔵 VÉHICULE' : '🟠 SUSPECT');
                const cardClass = e.qualification === 'RETENU' ? 'event-card retained' : (e.qualification === 'FAUX_POSITIF' ? 'event-card dismissed' : 'event-card');
                
                const chips = (e.obj_class || '').split(',').map(o => o.trim()).filter(Boolean);
                const chipsHtml = chips.map(o => `<div class="object-chip">${escapeHtml(o)}</div>`).join('');
                
                return `
                    <div class="${cardClass}" id="event-row-${e.id}">
                        <div class="event-image" data-snapshot="${escapeHtml(e.snapshot_path)}" data-title="${escapeHtml(e.filename)} — ${escapeHtml(e.timestamp_str)}">
                            <img src="/snapshots/${escapeHtml(e.snapshot_path)}" loading="lazy" alt="Snapshot Preuve">
                            <div class="zoom-icon">🔍</div>
                        </div>
                        <div class="event-details">
                            <div class="event-top">
                                <div class="event-title">📹 ${escapeHtml(e.filename)}</div>
                                <div class="event-meta">
                                    <span class="meta-tag ${sevClass}">${sevLabel}</span>
                                    <span class="meta-tag time">⏱ ${escapeHtml(e.timestamp_str)}</span>
                                    <span class="meta-tag people">👥 ${e.count_people} pers.</span>
                                    <span class="meta-tag conf">🎯 ${e.confidence}%</span>
                                </div>
                            </div>
                            <div class="event-objects">
                                <div class="objects-title">Objets Détectés</div>
                                <div class="object-chips">${chipsHtml}</div>
                            </div>
                            <div class="event-actions">
                                <button class="btn-qualif btn-retain" data-action="retain" data-id="${e.id}">⭐ Retenir Preuve</button>
                                <button class="btn-qualif btn-dismiss" data-action="dismiss" data-id="${e.id}">🗑️ Faux Positif</button>
                                <button class="btn-qualif" data-action="note" data-id="${e.id}" style="background:#e0f2fe; color:#0369a1;">📝 Note</button>
                                <span class="notes-preview" id="note-preview-${e.id}">${e.notes ? '💬 ' + escapeHtml(e.notes) : ''}</span>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Actions de qualification forensique
        document.addEventListener('click', function(evt) {
            const btn = evt.target.closest('button[data-action]');
            if (btn) {
                const action = btn.getAttribute('data-action');
                const id = btn.getAttribute('data-id');
                if (action === 'retain') {
                    qualifyEvent(id, 'RETENU');
                } else if (action === 'dismiss') {
                    qualifyEvent(id, 'FAUX_POSITIF');
                } else if (action === 'note') {
                    const currentNote = prompt("Ajouter une note d'enquête pour cette preuve :");
                    if (currentNote !== null) {
                        qualifyEvent(id, null, currentNote);
                    }
                }
                return;
            }

            // Ouverture du zoom image
            const imgBox = evt.target.closest('.event-image');
            if (imgBox) {
                const snap = imgBox.getAttribute('data-snapshot');
                const title = imgBox.getAttribute('data-title');
                openModal(`/snapshots/${snap}`, title);
            }
        });

        function qualifyEvent(id, qualification, notes) {
            const body = {};
            if (qualification) body.qualification = qualification;
            if (notes !== undefined) body.notes = notes;

            fetch(`/api/events/${id}/qualify`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    const ev = allEvents.find(e => e.id === Number(id));
                    if (ev) {
                        if (data.qualification) ev.qualification = data.qualification;
                        if (data.notes !== undefined) ev.notes = data.notes;
                    }
                    applyFilters();
                    loadStats();
                }
            })
            .catch(err => alert("Erreur qualification : " + err));
        }

        function openModal(path, caption) {
            document.getElementById('modalImage').src = path;
            document.getElementById('modalCaption').textContent = caption || '';
            document.getElementById('imageModal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('imageModal').classList.remove('active');
        }

        document.getElementById('modalClose').onclick = closeModal;
        document.getElementById('imageModal').onclick = function(e) {
            if (e.target === this) closeModal();
        };
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });

        // Listeners filtres
        ['filter-video', 'filter-severity', 'filter-qualification', 'filter-object', 'filter-people'].forEach(id => {
            document.getElementById(id).addEventListener('change', applyFilters);
        });

        document.getElementById('btn-refresh').onclick = function() {
            loadStats();
            loadEvents();
        };

        // Chargement initial et rafraîchissement automatique non bloquant
        loadStats();
        loadEvents();
        setInterval(function() {
            loadStats();
            loadEvents();
        }, 4000);
    </script>
</body>
</html>
"""

# --- TEMPLATE DU RAPPORT OFFICIEL D'INVESTIGATION ---
REPORT_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Rapport d'Investigation Forensique — Ocularis AI</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: 40px; color: #1e293b; line-height: 1.5; }
        .header { border-bottom: 3px solid #1e3a8a; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }
        .title h1 { font-size: 26px; color: #1e3a8a; margin-bottom: 4px; }
        .title p { color: #64748b; font-size: 14px; font-weight: 500; }
        .meta-box { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 18px; margin-bottom: 30px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; }
        .meta-item b { display: block; font-size: 11px; text-transform: uppercase; color: #64748b; margin-bottom: 4px; }
        .meta-item span { font-size: 18px; font-weight: 800; color: #0f172a; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 13px; }
        th { background: #1e293b; color: white; padding: 10px 12px; text-align: left; }
        td { padding: 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
        tr:nth-child(even) { background: #f8fafc; }
        .thumb { width: 120px; height: 80px; object-fit: cover; border-radius: 6px; border: 1px solid #cbd5e1; }
        .sev-crit { color: #dc2626; font-weight: bold; }
        .sev-susp { color: #d97706; font-weight: bold; }
        
        .signature-section { margin-top: 50px; display: grid; grid-template-columns: 1fr 1fr; gap: 40px; page-break-inside: avoid; }
        .sig-box { border: 1px dashed #94a3b8; border-radius: 8px; padding: 25px; min-height: 130px; }
        .sig-title { font-size: 12px; text-transform: uppercase; font-weight: 700; color: #64748b; margin-bottom: 10px; }
        
        .no-print { margin-bottom: 25px; }
        .btn-print { background: #1e3a8a; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: 700; border-radius: 6px; cursor: pointer; }
        @media print {
            .no-print { display: none; }
            body { padding: 0; }
        }
    </style>
</head>
<body>
    <div class="no-print">
        <button class="btn-print" onclick="window.print()">🖨️ Imprimer / Exporter en PDF</button>
    </div>

    <div class="header">
        <div class="title">
            <h1>RAPPORT FORENSIQUE D'INVESTIGATION VIDÉO</h1>
            <p>Ocularis AI — Système Universel d'Analyse Forensique Vidéo</p>
        </div>
        <div style="text-align: right; font-size: 13px; color: #64748b;">
            <b>Date d'édition :</b> {{ now }}<br>
            <b>Opérateur :</b> GHEMRI M (GM-Connect)
        </div>
    </div>

    <div class="meta-box">
        <div class="meta-item">
            <b>Vidéos Analysées</b>
            <span>{{ total_videos }}</span>
        </div>
        <div class="meta-item">
            <b>Alertes Détectées</b>
            <span>{{ total_events }}</span>
        </div>
        <div class="meta-item">
            <b>Preuves Retenues</b>
            <span style="color: #16a34a;">{{ retained_count }}</span>
        </div>
        <div class="meta-item">
            <b>Alertes Critiques</b>
            <span style="color: #dc2626;">{{ critical_count }}</span>
        </div>
    </div>

    <h2 style="font-size: 18px; margin-bottom: 10px; color: #1e293b;">Preuves Retenues & Événements Critiques d'Enquête</h2>
    <table>
        <thead>
            <tr>
                <th style="width: 130px;">Aperçu</th>
                <th>Caméra / Fichier Source</th>
                <th>Horodatage</th>
                <th>Sévérité</th>
                <th>Objets & Personnes</th>
                <th>Confiance</th>
                <th>Notes Enquêteur</th>
            </tr>
        </thead>
        <tbody>
            {% for ev in events %}
            <tr>
                <td>
                    <img class="thumb" src="/snapshots/{{ ev.snapshot_path }}" alt="Preuve">
                </td>
                <td><b>{{ ev.filename }}</b></td>
                <td>{{ ev.timestamp_str }}</td>
                <td class="{{ 'sev-crit' if ev.severity == 'CRITICAL' else 'sev-susp' }}">{{ ev.severity }}</td>
                <td>
                    <b>{{ ev.count_people }}</b> pers.<br>
                    <small style="color: #64748b;">{{ ev.obj_class }}</small>
                </td>
                <td>{{ ev.confidence }}%</td>
                <td>{{ ev.notes or '<i>Aucune note renseignée</i>' }}</td>
            </tr>
            {% else %}
            <tr>
                <td colspan="7" style="text-align: center; padding: 30px; color: #64748b;">
                    Aucune preuve n'a encore été marquée comme "Retenue" ou classée "Critique".
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="signature-section">
        <div class="sig-box">
            <div class="sig-title">Visa Enquêteur / Opérateur Forensique</div>
            <p style="font-size: 13px;">Nom : Ghemri M<br>Qualité : Responsable Système GM-Connect</p>
        </div>
        <div class="sig-box">
            <div class="sig-title">Visa Direction de la Sécurité / Autorité Compétente</div>
            <p style="font-size: 13px;">Date : ............................................<br>Signature & Cachet :</p>
        </div>
    </div>
</body>
</html>
"""


# --- ROUTES FLASK ---

@app.route('/')
def index():
    ensure_db()
    return render_template_string(HTML_TEMPLATE)


@app.route('/report')
def report():
    ensure_db()
    conn = get_db()
    cursor = conn.cursor()

    total_videos = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0] or 0
    total_events = cursor.execute("SELECT COUNT(*) FROM events").fetchone()[0] or 0
    retained_count = cursor.execute("SELECT COUNT(*) FROM events WHERE qualification='RETENU'").fetchone()[0] or 0
    critical_count = cursor.execute("SELECT COUNT(*) FROM events WHERE severity='CRITICAL'").fetchone()[0] or 0

    # Sélection des preuves retenues en priorité, ou des événements critiques
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

    import datetime
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

        # Requête des 500 derniers événements avec détails forensiques complets
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


if __name__ == '__main__':
    ensure_db()
    host = os.getenv("OCULARIS_WEB_HOST", os.getenv("GM_WEB_HOST", "0.0.0.0"))
    port = int(os.getenv("OCULARIS_WEB_PORT", os.getenv("GM_WEB_PORT", "5000")))
    debug_mode = os.getenv("OCULARIS_WEB_DEBUG", os.getenv("GM_WEB_DEBUG", "0")) in ("1", "true", "True")

    print("=" * 66)
    print("🚀 OCULARIS AI — Interface Web Forensique v1.1.0")
    print("   Système Universel d'Analyse Forensique Vidéo & Audit CCTV")
    print("=" * 66)
    print(f"📡 Serveur actif sur : http://localhost:{port}")
    print(f"📄 Rapport d'enquête : http://localhost:{port}/report")
    print(f"📥 Export CSV        : http://localhost:{port}/api/export/csv")
    print("=" * 66)

    app.run(debug=debug_mode, host=host, port=port)
