"""
OCULARIS AI - SUITE DE VALIDATION RTSP & FORENSIQUE V1.3.0
"""

import unittest
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from unittest.mock import patch
from rtsp_manager import (
    mask_rtsp_password,
    unmask_rtsp_password,
    check_person_object_proximity,
    create_placeholder_frame,
    test_rtsp_connection,
    MultiCameraRTSPManager
)
from web_interface import app, ensure_db


class TestOcularisRTSP(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        ensure_db()

    def test_01_password_masking(self):
        url = "rtsp://admin:SecretPass123@192.168.1.100:554/live"
        masked = mask_rtsp_password(url)
        self.assertEqual(masked, "rtsp://admin:******@192.168.1.100:554/live")

        # Unmasking test
        unmasked = unmask_rtsp_password("rtsp://admin:******@192.168.1.100:554/live", url)
        self.assertEqual(unmasked, url)

    def test_02_proximity_detection(self):
        # Personne [100, 100, 200, 300]
        # Objet [180, 150, 250, 220] (chevauchement)
        person_boxes = [(100, 100, 200, 300)]
        obj_boxes = [(180, 150, 250, 220)]
        self.assertTrue(check_person_object_proximity(person_boxes, obj_boxes, max_distance_px=220))

        # Objet très éloigné [800, 800, 900, 900]
        far_boxes = [(800, 800, 900, 900)]
        self.assertFalse(check_person_object_proximity(person_boxes, far_boxes, max_distance_px=100))

    def test_03_rtsp_manager_crud(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            temp_config = f.name

        try:
            mgr = MultiCameraRTSPManager(config_path=temp_config)
            # Add camera
            cam = mgr.add_or_update_camera({
                'id': 'test_cam_01',
                'name': 'Test Entree',
                'url': 'rtsp://admin:pass@127.0.0.1:554/stream',
                'enabled': False,
                'fps_analyze': 2.0,
                'cooldown_sec': 3.5
            })
            self.assertEqual(cam.camera_id, 'test_cam_01')
            self.assertIn('test_cam_01', mgr.streams)

            # Get list
            cams_list = mgr.get_cameras_list(mask_secret=True)
            self.assertTrue(any(c['id'] == 'test_cam_01' for c in cams_list))

            # Toggle camera
            mgr.toggle_camera('test_cam_01', enabled=True)
            self.assertTrue(mgr.streams['test_cam_01'].enabled)

            # Delete camera
            mgr.delete_camera('test_cam_01')
            self.assertNotIn('test_cam_01', mgr.streams)
        finally:
            if os.path.exists(temp_config):
                os.remove(temp_config)

    def test_04_api_cameras_endpoints(self):
        # GET /api/cameras
        res = self.client.get('/api/cameras')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('cameras', data)

        # POST /api/cameras
        res_post = self.client.post('/api/cameras', json={
            'id': 'cam_api_test',
            'name': 'API Cam Test',
            'url': 'rtsp://test:pass@192.168.1.200:554/ch1',
            'enabled': False,
            'fps_analyze': 2.0,
            'cooldown_sec': 3.5
        })
        self.assertEqual(res_post.status_code, 200)

        # POST /api/cameras/cam_api_test/toggle
        res_toggle = self.client.post('/api/cameras/cam_api_test/toggle', json={'enabled': False})
        self.assertEqual(res_toggle.status_code, 200)

        # DELETE /api/cameras/cam_api_test
        res_del = self.client.delete('/api/cameras/cam_api_test')
        self.assertEqual(res_del.status_code, 200)

    @patch('web_interface.test_rtsp_connection')
    def test_05_api_test_camera(self, mock_test_conn):
        # Test sans URL
        res_empty = self.client.post('/api/cameras/test', json={'url': ''})
        self.assertEqual(res_empty.status_code, 400)

        # Test avec fausse URL (doit répondre proprement sans crasher)
        mock_test_conn.return_value = {'success': False, 'error': 'Connection timeout'}
        res_fake = self.client.post('/api/cameras/test', json={'url': 'rtsp://127.0.0.1:9999/fake'})
        self.assertEqual(res_fake.status_code, 200)
        data = res_fake.get_json()
        self.assertIn('success', data)
        self.assertFalse(data['success'])

        # Test avec webcam locale '0'
        mock_test_conn.return_value = {'success': True, 'width': 640, 'height': 480, 'fps': 30.0}
        res_wc = self.client.post('/api/cameras/test', json={'url': '0'})
        self.assertEqual(res_wc.status_code, 200)
        data_wc = res_wc.get_json()
        self.assertIn('success', data_wc)
        self.assertTrue(data_wc['success'])

    def test_06_forensic_pages(self):
        # Dashboard principal
        res_home = self.client.get('/')
        self.assertEqual(res_home.status_code, 200)
        self.assertIn(b"Ocularis AI", res_home.data)
        self.assertIn(b"RTSP", res_home.data)

        # Stats
        res_stats = self.client.get('/api/stats')
        self.assertEqual(res_stats.status_code, 200)

        # Rapport Officiel
        res_report = self.client.get('/report')
        self.assertEqual(res_report.status_code, 200)
        self.assertIn(b"RAPPORT FORENSIQUE", res_report.data)

        # Export CSV
        res_csv = self.client.get('/api/export/csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, 'text/csv')

    def test_07_webcam_detection_and_open(self):
        from rtsp_manager import is_webcam_source
        # Test identification de webcam locale intégrée (0) ou externe (1)
        is_wc, val = is_webcam_source(0)
        self.assertTrue(is_wc)
        self.assertEqual(val, 0)

        is_wc, val = is_webcam_source("0")
        self.assertTrue(is_wc)
        self.assertEqual(val, 0)

        is_wc, val = is_webcam_source("1")
        self.assertTrue(is_wc)
        self.assertEqual(val, 1)

        # Test détection d'URL RTSP
        is_wc_rtsp, val_rtsp = is_webcam_source("rtsp://admin:pass@192.168.1.100:554/live")
        self.assertFalse(is_wc_rtsp)
        self.assertEqual(val_rtsp, "rtsp://admin:pass@192.168.1.100:554/live")

    def test_08_dynamic_classes_and_detection_catalog(self):
        # GET /api/detection-catalog
        res_cat = self.client.get('/api/detection-catalog')
        self.assertEqual(res_cat.status_code, 200)
        cat_data = res_cat.get_json()
        self.assertIn('supported_classes', cat_data)
        self.assertIn('person', cat_data['supported_classes'])
        self.assertIn('cell phone', cat_data['supported_classes'])

        # POST /api/cameras pour créer une caméra test avec classes
        self.client.post('/api/cameras', json={
            'id': 'cam_classes_test',
            'name': 'Camera Classes Test',
            'url': '0',
            'enabled': False,
            'target_classes': ['person', 'cell phone'],
            'trigger_mode': 'ANY_TARGET',
            'conf_threshold': 0.30
        })

        # POST /api/cameras/cam_classes_test/classes
        res_classes = self.client.post('/api/cameras/cam_classes_test/classes', json={
            'target_classes': ['car', 'motorcycle'],
            'trigger_mode': 'FORENSIC',
            'conf_threshold': 0.45
        })
        self.assertEqual(res_classes.status_code, 200)
        c_data = res_classes.get_json()
        self.assertEqual(c_data['camera']['target_classes'], ['car', 'motorcycle'])
        self.assertEqual(c_data['camera']['trigger_mode'], 'FORENSIC')
        self.assertEqual(c_data['camera']['conf_threshold'], 0.45)

        # Nettoyage
        self.client.delete('/api/cameras/cam_classes_test')

    def test_09_videos_folder_management(self):
        # GET /api/videos-folder
        res_info = self.client.get('/api/videos-folder')
        self.assertEqual(res_info.status_code, 200)
        data = res_info.get_json()
        self.assertIn('folder_path', data)
        self.assertIn('total_files', data)
        self.assertIn('files', data)
        self.assertIn('analysis_state', data)

        # POST /api/videos-folder/upload (test d'un fichier fictif .mp4)
        import io
        dummy_video = (io.BytesIO(b"dummy video content for ocularis test"), "unit_test_video.mp4")
        res_up = self.client.post('/api/videos-folder/upload', data={'files': dummy_video}, content_type='multipart/form-data')
        self.assertEqual(res_up.status_code, 200)
        up_data = res_up.get_json()
        self.assertTrue(up_data['ok'])
        self.assertIn('unit_test_video.mp4', up_data['saved'])

        # GET /api/videos-folder/analyze-status
        res_st = self.client.get('/api/videos-folder/analyze-status')
        self.assertEqual(res_st.status_code, 200)
        st_data = res_st.get_json()
        self.assertIn('is_running', st_data)
        self.assertIn('status', st_data)

        # POST /api/videos-folder/delete pour nettoyer le fichier de test
        res_del = self.client.post('/api/videos-folder/delete', json={'filename': 'unit_test_video.mp4'})
        self.assertEqual(res_del.status_code, 200)
        del_data = res_del.get_json()
        self.assertTrue(del_data['ok'])


if __name__ == '__main__':
    unittest.main()
