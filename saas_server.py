#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
SERVEUR BACKEND SAAS CLOUD & SYNCHRONISATION — STOCKCHANTIER PRO (v2)
Éditeur : YAR INFORMATIQUE — M. YAGO
Siège : Ouagadougou (Burkina Faso)
Téléphones : 64 58 22 02 / 67 93 05 50 — Email : yarinformatique@mail.com
=============================================================================
Ce serveur gère :
1. La Console Super-Admin centrale de M. YAGO (Gestion entreprises & PDG).
2. L'authentification des clients en ligne avec contrôle de licence.
3. La synchronisation bidirectionnelle Offline-First pour les chantiers.
4. La distribution de l'application cliente Web Hybride.
"""

import os
import sys
import json
import sqlite3
import hashlib
import uuid
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
import traceback

try:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    elif hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    elif hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    with open('crash.log', 'a') as f:
        traceback.print_exc(file=f)

PORT = int(os.environ.get('PORT', 9000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "stockchantier_saas.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table Super-Admin (M. YAGO)
    c.execute('''
        CREATE TABLE IF NOT EXISTS superadmin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT
        )
    ''')
    # Table Entreprises Clientes
    c.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT,
            ceo_name TEXT,
            ceo_email TEXT UNIQUE,
            ceo_password_hash TEXT,
            status TEXT DEFAULT 'active',
            currency TEXT DEFAULT 'FCFA',
            plan_duration TEXT DEFAULT '1_YEAR',
            created_at TEXT,
            expires_at TEXT,
            ceo_password_clear TEXT DEFAULT 'admin123',
            synced_state TEXT
        )
    ''')
    try:
        c.execute("ALTER TABLE companies ADD COLUMN ceo_password_clear TEXT DEFAULT 'admin123'")
    except sqlite3.OperationalError:
        pass

    # Table Entreprises Supprimées (Kill-Switch & historique)
    c.execute('''
        CREATE TABLE IF NOT EXISTS deleted_companies (
            code TEXT PRIMARY KEY,
            name TEXT,
            deleted_at TEXT
        )
    ''')

    # Table Séquences et Numérotations de Documents (Anti-doublons)
    c.execute('''
        CREATE TABLE IF NOT EXISTS company_document_sequences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_code TEXT,
            doc_type TEXT,
            prefix TEXT,
            period TEXT,
            last_seq INTEGER DEFAULT 0,
            UNIQUE(company_code, doc_type, prefix, period)
        )
    ''')

    # Créer ou mettre à jour le compte Super-Admin (strictement yarinformatique avec code 1762)
    pwd_1762 = hashlib.sha256("1762".encode()).hexdigest()
    c.execute('DELETE FROM superadmin')
    c.execute('''
        INSERT INTO superadmin (id, email, password_hash, name)
        VALUES (1, 'yarinformatique', ?, 'Direction YAR INFORMATIQUE — M. YAGO')
    ''', (pwd_1762,))
    
    conn.commit()
    conn.close()


CLOUD_SYNC_URL = "https://stockchantier-serveur.onrender.com"

def forward_action_to_cloud(action, code, payload=None):
    """Propage silencieusement en tâche de fond les actions SuperAdmin locales vers le Cloud Render."""
    if os.environ.get('RENDER'):
        return
    def _worker():
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            auth_bytes = base64.b64encode(b"yarinformatique:1762").decode("ascii")
            headers = {
                "Authorization": f"Basic {auth_bytes}",
                "Content-Type": "application/json"
            }
            if action == 'create':
                req = urllib.request.Request(f"{CLOUD_SYNC_URL}/api/superadmin/companies/create", data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
                urllib.request.urlopen(req, context=ctx, timeout=8)
                print(f"[CLOUD SYNC] Entreprise créée sur le Cloud: {code}")
                return

            req_list = urllib.request.Request(f"{CLOUD_SYNC_URL}/api/superadmin/companies", headers=headers)
            with urllib.request.urlopen(req_list, context=ctx, timeout=8) as r:
                cdata = json.loads(r.read().decode('utf-8'))
                comps = cdata.get('companies', []) if isinstance(cdata, dict) else cdata
                cloud_comp = next((c for c in comps if c.get('code') == code), None)

            if not cloud_comp:
                print(f"[CLOUD SYNC] Entreprise {code} introuvable sur le Cloud pour action {action}")
                return

            cloud_id = cloud_comp['id']
            if action == 'toggle':
                target_status = payload.get('status') if payload else None
                if not target_status or cloud_comp.get('status') != target_status:
                    req_t = urllib.request.Request(f"{CLOUD_SYNC_URL}/api/superadmin/companies/{cloud_id}/toggle", data=b"{}", headers=headers, method='POST')
                    urllib.request.urlopen(req_t, context=ctx, timeout=8)
                    print(f"[CLOUD SYNC] Statut synchronisé sur le Cloud pour {code}: {target_status}")
            elif action == 'delete':
                req_d = urllib.request.Request(f"{CLOUD_SYNC_URL}/api/superadmin/companies/{cloud_id}/delete", data=b"{}", headers=headers, method='POST')
                urllib.request.urlopen(req_d, context=ctx, timeout=8)
                print(f"[CLOUD SYNC] Entreprise {code} définitivement supprimée du Cloud.")
        except Exception as e:
            print(f"[CLOUD SYNC] Notification Cloud ({action} {code}): {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

class SaaSRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith('/api/superadmin/companies/'):
            try:
                parts = [p for p in path.split('/') if p]
                cid = int(parts[3])
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT name, code FROM companies WHERE id = ?', (cid,))
                row = c.fetchone()
                if not row:
                    conn.close()
                    self.send_json({'success': False, 'error': 'Entreprise introuvable'}, status=404)
                    return
                c_name, c_code = row[0], row[1]
                c.execute('INSERT OR REPLACE INTO deleted_companies (code, name, deleted_at) VALUES (?, ?, ?)', (c_code, c_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                c.execute('DELETE FROM companies WHERE id = ?', (cid,))
                conn.commit()
                conn.close()
                forward_action_to_cloud('delete', c_code, None)
                self.send_json({'success': True, 'message': f"L'entreprise '{c_name}' ({c_code}) a été définitivement supprimée."})
            except Exception as e:
                self.send_json({'success': False, 'error': str(e)}, status=500)
            return
        self.send_json({'success': False, 'error': 'Route non trouvée'}, status=404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Redirection vers la console Super-Admin
        if path in ('/superadmin', '/admin'):
            self.send_response(302)
            self.send_header('Location', '/superadmin_portal.html')
            self.end_headers()
            return

        # Redirection vers l'application cliente Hybride
        if path in ('/', '/app'):
            self.send_response(302)
            self.send_header('Location', '/app_hybrid.html')
            self.end_headers()
            return

        # Health check pour hébergement Cloud (Render, Railway, Fly.io, etc.)
        if path in ('/health', '/healthz', '/api/health'):
            self.send_json({'status': 'ok', 'service': 'StockChantier Pro Cloud Sync', 'version': '2.0.0'})
            return

        # API : Liste des entreprises pour le Super-Admin
        if path == '/api/superadmin/companies':
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, code, name, ceo_name, ceo_email, status, currency, plan_duration, created_at, expires_at, ceo_password_clear, synced_state FROM companies ORDER BY id DESC')
            rows = c.fetchall()
            conn.close()
            companies = []
            for r in rows:
                state = json.loads(r[11]) if r[11] else {}
                companies.append({
                    'id': r[0],
                    'code': r[1],
                    'name': r[2],
                    'ceo_name': r[3],
                    'ceo_email': r[4],
                    'status': r[5],
                    'currency': r[6],
                    'plan_duration': r[7],
                    'created_at': r[8],
                    'expires_at': r[9],
                    'ceo_password': r[10] or 'admin123',
                    'users': (lambda st: [u for i, u in enumerate(st.get('users', []) + st.get('initial_users', [])) if (u.get('email') or u.get('name')) not in [x.get('email') or x.get('name') for x in (st.get('users', []) + st.get('initial_users', []))[:i]]])(state)
                })
            self.send_json({'success': True, 'companies': companies})
            return

        # API : Vérification du statut de l'entreprise (Kill-switch distant)
        if path == '/api/client/status':
            query = urllib.parse.parse_qs(parsed.query)
            company_code = query.get('code', [''])[0].strip()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT name, deleted_at FROM deleted_companies WHERE code = ?', (company_code,))
            del_row = c.fetchone()
            if del_row:
                conn.close()
                self.send_json({'success': False, 'status': 'deleted', 'error': f"⛔ ACCÈS RÉVOQUÉ : L'entreprise '{del_row[0]}' a été définitivement supprimée par l'administrateur M. YAGO."}, status=403)
                return

            c.execute('SELECT id, status, name, expires_at FROM companies WHERE code = ?', (company_code,))
            row = c.fetchone()
            conn.close()
            if not row:
                self.send_json({'success': False, 'status': 'deleted', 'reason': 'ACCOUNT_DELETED', 'error': "⛔ ACCÈS RÉVOQUÉ : Cette entreprise n'existe plus ou a été supprimée."}, status=404)
                return
            if row[1] != 'active':
                self.send_json({'success': False, 'status': 'suspended', 'error': "⛔ ACCÈS SUSPENDU : L'accès de cette entreprise a été suspendu par l'administrateur M. YAGO."}, status=403)
                return
            self.send_json({'success': True, 'status': 'active', 'name': row[2], 'expires_at': row[3]})
            return

        # API : Récupération de la configuration pour un client
        if path == '/api/client/pull':
            query = urllib.parse.parse_qs(parsed.query)
            company_code = query.get('code', [''])[0]
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, code, name, ceo_name, status, currency, expires_at, synced_state FROM companies WHERE code = ?', (company_code,))
            row = c.fetchone()
            conn.close()
            if not row:
                self.send_json({'success': False, 'error': 'Entreprise introuvable'}, status=404)
                return
            if row[4] != 'active':
                self.send_json({'success': False, 'error': 'Accès suspendu par l\'éditeur'}, status=403)
                return
            self.send_json({
                'success': True,
                'company': {
                    'id': row[0],
                    'code': row[1],
                    'name': row[2],
                    'ceo_name': row[3],
                    'status': row[4],
                    'currency': row[5],
                    'expires_at': row[6],
                    'synced_state': json.loads(row[7]) if row[7] else {}
                }
            })
            return

        # Fichiers statiques normaux
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(length) if length > 0 else b'{}'
        try:
            body = json.loads(post_data.decode('utf-8'))
        except Exception:
            body = {}

        # API : Vérification du statut de l'entreprise en POST (Kill-switch distant)
        if path == '/api/client/status':
            company_code = body.get('code', '').strip()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT name, deleted_at FROM deleted_companies WHERE code = ?', (company_code,))
            del_row = c.fetchone()
            if del_row:
                conn.close()
                self.send_json({'success': False, 'status': 'deleted', 'error': f"⛔ ACCÈS RÉVOQUÉ : L'entreprise '{del_row[0]}' a été définitivement supprimée par l'administrateur M. YAGO."}, status=403)
                return

            c.execute('SELECT id, status, name, expires_at FROM companies WHERE code = ?', (company_code,))
            row = c.fetchone()
            conn.close()
            if not row:
                self.send_json({'success': False, 'status': 'deleted', 'reason': 'ACCOUNT_DELETED', 'error': "⛔ ACCÈS RÉVOQUÉ : Cette entreprise n'existe plus ou a été supprimée."}, status=404)
                return
            if row[1] != 'active':
                self.send_json({'success': False, 'status': 'suspended', 'error': "⛔ ACCÈS SUSPENDU : L'accès de cette entreprise a été suspendu par l'administrateur M. YAGO."}, status=403)
                return
            self.send_json({'success': True, 'status': 'active', 'name': row[2], 'expires_at': row[3]})
            return

        # API : Enregistrement ou mise à jour automatique d'une entreprise activée par Pass
        if path == '/api/client/company/register':
            code = body.get('code', '').strip()
            name = body.get('name', '').strip()
            ceo_name = body.get('ceo_name', '').strip()
            ceo_email = body.get('ceo_email', '').strip() or ceo_name
            password = body.get('ceo_password', '').strip() or 'admin123'
            currency = body.get('currency', 'FCFA').strip()
            expires_at = body.get('expires_at', '31/12/2030').strip()
            users = body.get('users', [])

            if not code or not name:
                self.send_json({'success': False, 'error': "Code et Nom d'entreprise requis"}, status=400)
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, status, synced_state FROM companies WHERE code = ?', (code,))
            row = c.fetchone()
            if row:
                state = json.loads(row[2]) if row[2] else {}
                if users:
                    state['users'] = users
                c.execute('UPDATE companies SET synced_state = ? WHERE code = ?', (json.dumps(state), code))
                conn.commit()
                conn.close()
                self.send_json({'success': True, 'status': row[1], 'message': 'Entreprise déjà enregistrée sur le serveur'})
                return

            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            initial_state = {
                'users': users,
                'last_sync': datetime.now().strftime('%d/%m/%Y %H:%M')
            }
            try:
                c.execute('''
                    INSERT INTO companies (code, name, ceo_name, ceo_email, ceo_password_hash, ceo_password_clear, status, currency, plan_duration, created_at, expires_at, synced_state)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, '1_YEAR', ?, ?, ?)
                ''', (code, name, ceo_name, ceo_email, pwd_hash, password, currency, datetime.now().strftime('%d/%m/%Y'), '2030-12-31', json.dumps(initial_state)))
                conn.commit()
                conn.close()
                self.send_json({'success': True, 'status': 'active', 'message': 'Entreprise synchronisée avec succès sur le Cloud !'})
            except Exception as e:
                conn.close()
                self.send_json({'success': False, 'error': str(e)}, status=500)
            return

        # API : Génération et réservation atomique d'un numéro de document officiel (Anti-doublon)
        if path == '/api/documents/next-number':
            company_code = body.get('company_code', 'DEFAULT').strip()
            doc_type = body.get('doc_type', '').strip().upper() # BR, BL_FOURNISSEUR, BL_CHANTIER, RETOUR
            prefix = body.get('prefix', '').strip().upper()
            period = body.get('period', '').strip().upper() # Ex: '2610', '26', 'GLOBAL'

            if not doc_type or not prefix:
                self.send_json({'success': False, 'error': 'doc_type et prefix requis'}, status=400)
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            try:
                c.execute('''
                    INSERT INTO company_document_sequences (company_code, doc_type, prefix, period, last_seq)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(company_code, doc_type, prefix, period)
                    DO UPDATE SET last_seq = last_seq + 1
                ''', (company_code, doc_type, prefix, period))
                conn.commit()

                c.execute('''
                    SELECT last_seq FROM company_document_sequences
                    WHERE company_code = ? AND doc_type = ? AND prefix = ? AND period = ?
                ''', (company_code, doc_type, prefix, period))
                row = c.fetchone()
                seq = row[0] if row else 1

                seq_str = f"{seq:03d}"
                if doc_type == 'BR':
                    doc_number = f"BR-{prefix}-{period}-{seq_str}"
                elif doc_type == 'BL_FOURNISSEUR':
                    doc_number = f"BL-{prefix}-{seq_str}"
                elif doc_type == 'BL_CHANTIER':
                    doc_number = f"BL-{prefix}-{period}-{seq_str}"
                elif doc_type == 'RETOUR':
                    doc_number = f"RET-{prefix}-{period}-{seq_str}"
                else:
                    doc_number = f"{doc_type}-{prefix}-{period}-{seq_str}"

                conn.close()
                self.send_json({
                    'success': True,
                    'number': doc_number,
                    'sequence': seq,
                    'doc_type': doc_type,
                    'prefix': prefix,
                    'period': period
                })
            except Exception as e:
                conn.close()
                self.send_json({'success': False, 'error': str(e)}, status=500)
            return

        # 1. Login Super-Admin (YAR INFORMATIQUE — M. YAGO)
        if path == '/api/superadmin/login':
            identifier = body.get('email', '').strip().lower()
            password = body.get('password', '').strip()

            # Super-Admin exclusif : strictement 'yarinformatique' et '1762'
            if identifier == 'yarinformatique' and password == '1762':
                self.send_json({
                    'success': True,
                    'token': str(uuid.uuid4()),
                    'name': 'Direction YAR INFORMATIQUE — M. YAGO',
                    'email': 'yarinformatique'
                })
            else:
                self.send_json({'success': False, 'error': 'Identifiant ou code secret incorrect.'}, status=401)
            return

        # 2. Création d'une nouvelle entreprise cliente par M. YAGO
        if path == '/api/superadmin/companies/create':
            name = body.get('name', '').strip()
            ceo_name = body.get('ceo_name', '').strip()
            ceo_email = body.get('ceo_email', '').strip()
            password = body.get('password', '').strip()
            currency = body.get('currency', 'FCFA').strip()
            duration = body.get('duration', '1_YEAR')

            if not name or not ceo_name or not password:
                self.send_json({'success': False, 'error': 'Champs obligatoires manquants (Nom entreprise, PDG, Code)'}, status=400)
                return

            if not ceo_email:
                ceo_email = ceo_name # Utilise le nom comme identifiant si pas d'email

            now = datetime.now()
            if duration == '1_MONTH':
                exp = now + timedelta(days=31)
            elif duration == '3_MONTHS':
                exp = now + timedelta(days=92)
            elif duration == '6_MONTHS':
                exp = now + timedelta(days=183)
            elif duration == '1_YEAR':
                exp = now + timedelta(days=365)
            elif duration == 'LIFETIME':
                exp = now + timedelta(days=3650)
            else:
                exp = now + timedelta(days=365)

            code = f"COMP-{uuid.uuid4().hex[:6].upper()}"
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()

            chef_name = body.get('chef_name', '').strip()
            chef_email = body.get('chef_email', '').strip()
            chef_pass = body.get('chef_pass', '').strip()

            initial_state = {
                'movements_count': 0,
                'last_sync': now.strftime('%d/%m/%Y %H:%M'),
                'initial_users': []
            }
            if chef_name or chef_email:
                initial_state['initial_users'].append({
                    'id': f'usr-{uuid.uuid4().hex[:6]}',
                    'name': chef_name or 'Chef de Chantier',
                    'email': chef_email or chef_name,
                    'password': chef_pass or 'chef123',
                    'role': 'chef_chantier',
                    'status': 'Actif'
                })

            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('''
                    INSERT INTO companies (code, name, ceo_name, ceo_email, ceo_password_hash, ceo_password_clear, status, currency, plan_duration, created_at, expires_at, synced_state)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                ''', (
                    code, name, ceo_name, ceo_email, pwd_hash, password, currency, duration,
                    now.strftime('%Y-%m-%d %H:%M:%S'), exp.strftime('%Y-%m-%d'),
                    json.dumps(initial_state)
                ))
                new_id = c.lastrowid
                conn.commit()
                conn.close()

                self.send_json({
                    'success': True,
                    'message': 'Entreprise créée avec succès',
                    'company': {
                        'id': new_id,
                        'code': code,
                        'name': name,
                        'ceo_name': ceo_name,
                        'ceo_email': ceo_email,
                        'ceo_password': password,
                        'currency': currency,
                        'expires_at': exp.strftime('%d/%m/%Y'),
                        'duration': duration,
                        'users': initial_state['initial_users']
                    }
                })
            except sqlite3.IntegrityError:
                self.send_json({'success': False, 'error': 'Cet identifiant de PDG est déjà utilisé par une autre entreprise'}, status=400)
            return

        # 3. Réinitialisation / Modification d'un mot de passe par Abdoul YAGO
        if path.startswith('/api/superadmin/companies/') and path.endswith('/reset-password'):
            try:
                cid = int(path.split('/')[4])
                target = body.get('target', 'ceo')
                new_pwd = body.get('new_password', '').strip()
                if not new_pwd:
                    self.send_json({'success': False, 'error': 'Nouveau code d\'accès requis'}, status=400)
                    return
                new_hash = hashlib.sha256(new_pwd.encode()).hexdigest()

                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                if target == 'ceo':
                    c.execute('UPDATE companies SET ceo_password_hash = ?, ceo_password_clear = ? WHERE id = ?', (new_hash, new_pwd, cid))
                else:
                    c.execute('SELECT synced_state FROM companies WHERE id = ?', (cid,))
                    row = c.fetchone()
                    if row and row[0]:
                        st = json.loads(row[0])
                        for u in st.get('initial_users', []) + st.get('users', []):
                            if u.get('name') == target or u.get('email') == target or u.get('id') == target:
                                u['password'] = new_pwd
                        c.execute('UPDATE companies SET synced_state = ? WHERE id = ?', (json.dumps(st), cid))
                conn.commit()
                conn.close()
                self.send_json({'success': True, 'new_password': new_pwd, 'message': 'Code d\'accès mis à jour avec succès.'})
            except Exception as e:
                self.send_json({'success': False, 'error': str(e)}, status=500)
            return

        # 4. Bascule Actif / Suspendu (Kill-Switch à distance)
        if path.startswith('/api/superadmin/companies/') and path.endswith('/toggle'):
            try:
                cid = int(path.split('/')[4])
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT status FROM companies WHERE id = ?', (cid,))
                row = c.fetchone()
                if not row:
                    conn.close()
                    self.send_json({'success': False, 'error': 'Entreprise non trouvée'}, status=404)
                    return
                new_status = 'suspended' if row[0] == 'active' else 'active'
                c.execute('UPDATE companies SET status = ? WHERE id = ?', (new_status, cid))
                if new_status == 'active':
                    c.execute('SELECT code FROM companies WHERE id = ?', (cid,))
                    c_row = c.fetchone()
                    if c_row:
                        c.execute('DELETE FROM deleted_companies WHERE code = ?', (c_row[0],))
                conn.commit()
                # Récupérer le code de l'entreprise pour réplication Cloud
                c.execute('SELECT code FROM companies WHERE id = ?', (cid,))
                c_code_row = c.fetchone()
                c_code_target = c_code_row[0] if c_code_row else ''
                conn.close()
                if c_code_target:
                    forward_action_to_cloud('toggle', c_code_target, {'status': new_status})
                self.send_json({'success': True, 'new_status': new_status})
            except Exception as e:
                self.send_json({'success': False, 'error': str(e)}, status=500)
            return

        # 4b. Suppression Définitive d'une Entreprise par M. YAGO
        if path.startswith('/api/superadmin/companies/') and path.endswith('/delete'):
            try:
                cid = int(path.split('/')[4])
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute('SELECT name, code FROM companies WHERE id = ?', (cid,))
                row = c.fetchone()
                if not row:
                    conn.close()
                    self.send_json({'success': False, 'error': 'Entreprise non trouvée'}, status=404)
                    return
                c_name, c_code = row[0], row[1]
                c.execute('INSERT OR REPLACE INTO deleted_companies (code, name, deleted_at) VALUES (?, ?, ?)', (c_code, c_name, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                c.execute('DELETE FROM companies WHERE id = ?', (cid,))
                conn.commit()
                conn.close()
                forward_action_to_cloud('delete', c_code, None)
                self.send_json({'success': True, 'message': f"L'entreprise '{c_name}' ({c_code}) a été définitivement supprimée."})
            except Exception as e:
                self.send_json({'success': False, 'error': str(e)}, status=500)
            return

                # 4c. Synchronisation des Utilisateurs créés/modifiés par le PDG
        if path == '/api/client/sync/users':
            company_code = body.get('code', '')
            company_users = body.get('users', [])
            if not company_code:
                self.send_json({'success': False, 'error': 'Code entreprise requis'}, status=400)
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, status, synced_state FROM companies WHERE code = ?', (company_code,))
            row = c.fetchone()
            if not row:
                conn.close()
                self.send_json({'success': False, 'error': 'Entreprise introuvable'}, status=404)
                return

            if row[1] != 'active':
                conn.close()
                self.send_json({'success': False, 'error': 'Entreprise suspendue'}, status=403)
                return

            state = json.loads(row[2]) if row[2] else {}
            state['users'] = company_users
            state['last_users_sync'] = datetime.now().strftime('%d/%m/%Y %H:%M')

            c.execute('UPDATE companies SET synced_state = ? WHERE code = ?', (json.dumps(state), company_code))
            conn.commit()
            conn.close()

            self.send_json({
                'success': True,
                'message': f'{len(company_users)} utilisateur(s) synchronisé(s) avec succès !',
                'users_count': len(company_users)
            })
            return

        # 5. Connexion Client en Ligne (Vérification et initialisation)
        if path == '/api/client/login':
            identifier = body.get('email', '').strip().lower()
            password = body.get('password', '').strip()
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            # 1. Vérifier si l'identifiant existe parmi les dirigeants d'entreprise (PDG)
            c.execute('''
                SELECT id, code, name, ceo_name, status, currency, expires_at, synced_state, ceo_password_clear, ceo_password_hash, ceo_email
                FROM companies 
                WHERE (LOWER(ceo_email) = ? OR LOWER(ceo_name) = ?)
            ''', (identifier, identifier))
            comp_row = c.fetchone()

            target_user = None
            found_company = None

            if comp_row:
                found_company = comp_row
                target_user = {
                    'id': 'usr-ceo-' + str(comp_row[0]),
                    'name': comp_row[3],
                    'email': comp_row[10] or comp_row[3],
                    'role': 'admin',
                    'pwd_hash': comp_row[9],
                    'pwd_clear': comp_row[8]
                }
            else:
                # Chercher parmi les collaborateurs de l'entreprise (Chefs de chantier, magasiniers)
                c.execute('SELECT id, code, name, ceo_name, status, currency, expires_at, synced_state, ceo_password_clear, ceo_password_hash, ceo_email FROM companies')
                all_comps = c.fetchall()
                for comp in all_comps:
                    state = json.loads(comp[7]) if comp[7] else {}
                    users = state.get('users', []) + state.get('initial_users', [])
                    for u in users:
                        u_name = (u.get('name') or '').lower().strip()
                        u_email = (u.get('email') or '').lower().strip()
                        if u_email == identifier or u_name == identifier:
                            found_company = comp
                            target_user = {
                                'id': u.get('id') or ('usr-collab-' + str(comp[0])),
                                'name': u.get('name'),
                                'email': u.get('email') or u.get('name'),
                                'role': u.get('role', 'magasinier'),
                                'pwd_hash': hashlib.sha256(str(u.get('password', '')).encode()).hexdigest(),
                                'pwd_clear': str(u.get('password', ''))
                            }
                            break
                    if found_company:
                        break
            conn.close()

            # CAS A : L'identifiant n'existe PAS dans la base de données (ou entreprise supprimée)
            if not found_company or not target_user:
                self.send_json({
                    'success': False, 
                    'status': 'not_found',
                    'reason': 'ACCOUNT_NOT_FOUND',
                    'error': "Aucun compte n'est associé à cet identifiant ou l'entreprise a été supprimée."
                }, status=404)
                return

            # CAS B : Entreprise suspendue (Vérifié immédiatement avant tout le reste)
            if found_company[4] != 'active':
                self.send_json({
                    'success': False, 
                    'status': 'suspended',
                    'reason': 'SUSPENDED',
                    'error': "Compte d'entreprise suspendu. Contactez votre éditeur M. YAGO (YAR INFORMATIQUE)."
                }, status=403)
                return

            # CAS C : L'identifiant existe, mais le mot de passe est INCORRECT
            valid_pwd = (target_user['pwd_hash'] == pwd_hash or target_user['pwd_clear'] == password)
            if not valid_pwd:
                self.send_json({
                    'success': False, 
                    'reason': 'WRONG_PASSWORD',
                    'error': "Mot de passe incorrect pour cet identifiant."
                }, status=401)
                return

            # CAS D : Abonnement expiré
            exp_date = datetime.strptime(found_company[6], '%Y-%m-%d')
            if datetime.now() > exp_date:
                self.send_json({
                    'success': False, 
                    'reason': 'EXPIRED',
                    'error': f"Votre abonnement a expiré le {exp_date.strftime('%d/%m/%Y')}. Contactez M. YAGO pour renouveler."
                }, status=403)
                return

            # CAS E : Succès total
            self.send_json({
                'success': True,
                'token': str(uuid.uuid4()),
                'user': {
                    'name': target_user['name'],
                    'email': target_user['email'],
                    'role': target_user['role']
                },
                'company': {
                    'id': found_company[0],
                    'code': found_company[1],
                    'name': found_company[2],
                    'ceo_name': found_company[3],
                    'currency': found_company[5],
                    'expires_at': exp_date.strftime('%d/%m/%Y'),
                    'synced_state': json.loads(found_company[7]) if found_company[7] else {}
                }
            })
            return

        # 5. Synchronisation des mouvements hors-ligne
        if path == '/api/client/sync/push':
            company_code = body.get('code', '')
            offline_movements = body.get('movements', [])
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('SELECT id, status, synced_state FROM companies WHERE code = ?', (company_code,))
            row = c.fetchone()
            if not row:
                conn.close()
                self.send_json({'success': False, 'error': 'Entreprise introuvable'}, status=404)
                return
            
            if row[1] != 'active':
                conn.close()
                self.send_json({'success': False, 'error': 'Entreprise suspendue'}, status=403)
                return

            now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
            state = json.loads(row[2]) if row[2] else {}
            existing_count = state.get('movements_count', 0)
            new_count = existing_count + len(offline_movements)
            state['movements_count'] = new_count
            state['last_sync'] = now_str
            state['latest_batch'] = offline_movements[-10:]  # Garde les 10 derniers

            c.execute('UPDATE companies SET synced_state = ? WHERE code = ?', (json.dumps(state), company_code))
            conn.commit()
            conn.close()

            self.send_json({
                'success': True,
                'message': f'{len(offline_movements)} mouvement(s) synchronisé(s) avec succès !',
                'synced_at': now_str,
                'total_synced': new_count
            })
            return

        super().do_POST()

def main():
    import webbrowser
    import threading
    import time

    try:
        init_db()
        ThreadingHTTPServer.allow_reuse_address = True
        server = ThreadingHTTPServer(('0.0.0.0', PORT), SaaSRequestHandler)

        print("\n" + "=" * 66)
        print("   STOCKCHANTIER PRO — SERVEUR DE SYNCHRONISATION EN LIGNE")
        print(f"   * Statut              : ACTIF ET EN ÉCOUTE (Port {PORT})")
        print(f"   * Console Super-Admin : http://localhost:{PORT}/superadmin_portal.html")
        print(f"   * API Synchronisation : http://localhost:{PORT}/api/client/pull")
        print("   Éditeur : YAR INFORMATIQUE — M. YAGO (Ouagadougou)")
        print("=" * 66)
        print("   Ce serveur synchronise les données entre le chantier et le siège.")
        print("   Laissez cette fenêtre ouverte. Pour arrêter : Fermez la fenêtre.\n")

        # Ouverture automatique et garantie du portail Super-Admin après le démarrage du socket
        def open_browser():
            time.sleep(1.0)
            try:
                webbrowser.open(f'http://localhost:{PORT}/superadmin_portal.html')
            except Exception:
                pass

        threading.Thread(target=open_browser, daemon=True).start()

        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Arrêt du serveur par l'utilisateur.")
    except OSError as e:
        print(f"\n[AVERTISSEMENT] Port {PORT} déjà occupé ({e}).")
        print(f"La console est accessible sur http://localhost:{PORT}/superadmin_portal.html")
        try:
            webbrowser.open(f'http://localhost:{PORT}/superadmin_portal.html')
        except Exception:
            pass
    except Exception as e:
        print(f"\n[ERREUR SERVEUR] {e}")
        with open(os.path.join(BASE_DIR, 'crash.log'), 'w', encoding='utf-8') as f:
            traceback.print_exc(file=f)

if __name__ == '__main__':
    main()
