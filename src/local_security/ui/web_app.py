"""
Local Web Dashboard Server for Local Privacy & Security Module.
Serves a responsive, accessible security dashboard at http://127.0.0.1:8080
connecting to the same SecurityManager and SQLCipher encrypted database.
"""
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

from local_security.core.configuration import SecurityConfig
from local_security.core.exceptions import (
    InvalidCredentialsError,
    PINLockedError,
)
from local_security.core.security_manager import SecurityManager
from local_security.models.records import MemoryRecord

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Memory Companion - Security & Privacy Center</title>
  <style>
    :root {
      --bg: #0F1115;
      --card-bg: #161A22;
      --border: #28303F;
      --primary: #2563EB;
      --primary-hover: #1D4ED8;
      --text: #F1F5F9;
      --text-muted: #94A3B8;
      --success-bg: #064E3B;
      --success-text: #34D399;
      --danger: #EF4444;
      --warning-bg: #78350F;
      --warning-text: #FBBF24;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      padding: 24px;
      line-height: 1.5;
    }
    .container { max-width: 1040px; margin: 0 auto; }
    header {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border);
    }
    h1 { font-size: 24px; font-weight: 700; }
    .badge {
      display: inline-block; padding: 4px 12px; border-radius: 9999px;
      font-size: 13px; font-weight: 600;
    }
    .badge-success { background: var(--success-bg); color: var(--success-text); }
    .badge-danger { background: #450A0A; color: #F87171; }
    .btn {
      background: var(--primary); color: #fff; border: none; padding: 8px 16px;
      border-radius: 6px; font-weight: 600; cursor: pointer; transition: 0.15s;
    }
    .btn:hover { background: var(--primary-hover); }
    .btn-secondary { background: #1E293B; color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover { background: #334155; }
    .btn-danger { background: var(--danger); color: #fff; }
    .btn-danger:hover { background: #DC2626; }

    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
    .card {
      background: var(--card-bg); border: 1px solid var(--border);
      border-radius: 10px; padding: 20px;
    }
    .card h2 { font-size: 17px; margin-bottom: 12px; color: #38BDF8; }
    .meta-item { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; }
    .meta-label { color: var(--text-muted); }

    .tabs { display: flex; gap: 8px; margin-bottom: 16px; border-bottom: 1px solid var(--border); }
    .tab-btn {
      background: none; border: none; padding: 10px 18px; color: var(--text-muted);
      font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent;
    }
    .tab-btn.active { color: #38BDF8; border-bottom: 2px solid #38BDF8; }

    input, textarea, select {
      width: 100%; background: #1E2430; border: 1px solid #334155;
      color: var(--text); padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px;
    }
    input:focus, textarea:focus { outline: none; border-color: #38BDF8; }

    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
    th, td { text-align: left; padding: 10px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-size: 13px; text-transform: uppercase; }

    /* Lock Overlay */
    #lock-modal {
      position: fixed; inset: 0; background: rgba(11, 13, 17, 0.95);
      display: flex; justify-content: center; align-items: center; z-index: 1000;
    }
    .lock-card {
      background: var(--card-bg); border: 1px solid var(--border);
      border-radius: 12px; padding: 32px; width: 420px; text-align: center;
    }
    .lock-card h2 { margin-bottom: 8px; font-size: 20px; }
    .lock-card p { color: var(--text-muted); font-size: 14px; margin-bottom: 20px; }
    .alert-error { color: #EF4444; font-size: 13px; margin-top: 8px; font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Personal Memory Companion</h1>
        <p style="color: var(--text-muted); font-size: 13px;">Local-First Privacy & Security Center</p>
      </div>
      <div style="display: flex; gap: 12px; align-items: center;">
        <span class="badge badge-success">100% Offline / Local-Only</span>
        <span id="lock-badge" class="badge badge-success">UNLOCKED</span>
        <button id="lock-btn" class="btn btn-danger" onclick="lockVault()">Lock Now</button>
      </div>
    </header>

    <!-- Top Metrics Grid -->
    <div class="grid">
      <div class="card">
        <h2>Encrypted Storage (SQLCipher 4.12)</h2>
        <div class="meta-item"><span class="meta-label">Cipher Engine:</span><span id="cipher-ver">Loading...</span></div>
        <div class="meta-item"><span class="meta-label">Page Size:</span><span>4096 bytes</span></div>
        <div class="meta-item"><span class="meta-label">PBKDF2 Iterations:</span><span>256,000 (HMAC-SHA512)</span></div>
        <div class="meta-item"><span class="meta-label">Database File:</span><span id="db-filename">vault.enc.db</span></div>
        <button class="btn btn-secondary" style="margin-top: 10px; width: 100%;" onclick="runDiskAudit()">Run On-Disk Entropy & Plaintext Audit</button>
      </div>
      <div class="card">
        <h2>Authentication & Platform Security</h2>
        <div class="meta-item"><span class="meta-label">Key Protection:</span><span id="key-backend">Windows DPAPI</span></div>
        <div class="meta-item"><span class="meta-label">PIN Security:</span><span>Argon2id (Salted & Rate-limited)</span></div>
        <div class="meta-item"><span class="meta-label">OS Biometrics:</span><span id="bio-status">Checking...</span></div>
        <div class="meta-item"><span class="meta-label">Active User:</span><span id="active-user">None</span></div>
        <button class="btn btn-secondary" style="margin-top: 10px; width: 100%;" onclick="rotateKey()">Rotate Database Encryption Key</button>
      </div>
    </div>

    <!-- Main Navigation Tabs -->
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('storage')">Encrypted Memories (FTS5)</button>
      <button class="tab-btn" onclick="switchTab('audit')">Security Audit Log</button>
    </div>

    <!-- Storage Tab -->
    <div id="tab-storage" class="card">
      <div style="display: flex; gap: 10px; margin-bottom: 16px;">
        <input type="text" id="search-input" placeholder="Search encrypted memories using FTS5 (e.g. walk, medication, family)..." onkeyup="if(event.key==='Enter') searchMemories()">
        <button class="btn" style="width: 120px;" onclick="searchMemories()">Search</button>
      </div>

      <div style="background: #11141B; padding: 16px; border-radius: 8px; margin-bottom: 20px; border: 1px solid var(--border);">
        <h3 style="font-size: 15px; margin-bottom: 10px; color: #E2E8F0;">+ Add Encrypted Memory</h3>
        <input type="text" id="new-title" placeholder="Memory Title (e.g. Morning Medication Schedule)">
        <textarea id="new-content" rows="2" placeholder="Details to encrypt locally with SQLCipher..."></textarea>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <label style="font-size: 13px; color: var(--text-muted);">
            <input type="checkbox" id="new-caregiver" style="width: auto; margin-right: 6px;"> Share with Caregiver Dashboard
          </label>
          <button class="btn" onclick="addMemory()">Save Encrypted Memory</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Content Preview</th>
            <th>Category</th>
            <th>Caregiver Shared</th>
          </tr>
        </thead>
        <tbody id="memories-tbody">
          <tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Loading memories...</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Audit Tab -->
    <div id="tab-audit" class="card" style="display: none;">
      <h2>Immutable Security Audit Events</h2>
      <table>
        <thead>
          <tr>
            <th>Timestamp (UTC)</th>
            <th>Event Type</th>
            <th>Actor</th>
            <th>Module</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody id="audit-tbody">
          <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading audit events...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Lock Modal Overlay -->
  <div id="lock-modal" style="display: none;">
    <div class="lock-card">
      <div style="font-size: 42px; margin-bottom: 12px;">🔒</div>
      <h2>Memory Companion Locked</h2>
      <p>Personal data is encrypted. Enter your security PIN to unlock.</p>
      <input type="password" id="unlock-pin" placeholder="Enter Security PIN" style="font-size: 18px; text-align: center;" onkeyup="if(event.key==='Enter') submitUnlock()">
      <button class="btn" style="width: 100%; margin-top: 8px;" onclick="submitUnlock()">Unlock Vault</button>
      <div id="lock-error" class="alert-error"></div>
    </div>
  </div>

  <script>
    async function loadStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('cipher-ver').innerText = 'SQLCipher ' + data.cipher_version;
        document.getElementById('db-filename').innerText = data.database_filename;
        document.getElementById('key-backend').innerText = data.key_backend;
        document.getElementById('bio-status').innerText = data.biometrics.available ? 'Available (Windows Hello)' : data.biometrics.code;
        document.getElementById('active-user').innerText = data.user ? (data.user.display_name + ' (@' + data.user.username + ')') : 'None';

        if (data.is_locked) {
          document.getElementById('lock-badge').className = 'badge badge-danger';
          document.getElementById('lock-badge').innerText = 'LOCKED';
          document.getElementById('lock-modal').style.display = 'flex';
        } else {
          document.getElementById('lock-badge').className = 'badge badge-success';
          document.getElementById('lock-badge').innerText = 'UNLOCKED';
          document.getElementById('lock-modal').style.display = 'none';
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function searchMemories() {
      const q = document.getElementById('search-input').value.trim();
      const res = await fetch('/api/memories?q=' + encodeURIComponent(q));
      const data = await res.json();
      const tbody = document.getElementById('memories-tbody');
      tbody.innerHTML = '';
      if (!data.memories || data.memories.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No records found.</td></tr>';
        return;
      }
      data.memories.forEach(m => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-weight: 600;">${m.title}</td>
          <td style="color: #CBD5E1;">${m.content.length > 70 ? m.content.substring(0, 70) + '...' : m.content}</td>
          <td><span class="badge" style="background:#1E293B; color:#94A3B8;">${m.category}</span></td>
          <td>${m.is_shared_with_caregiver ? '<span class="badge badge-success">Shared</span>' : '<span style="color:#64748B;">Private</span>'}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function addMemory() {
      const title = document.getElementById('new-title').value.trim();
      const content = document.getElementById('new-content').value.trim();
      const isShared = document.getElementById('new-caregiver').checked;
      if (!title || !content) return alert('Please enter title and content.');

      await fetch('/api/memories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content, is_shared_with_caregiver: isShared })
      });
      document.getElementById('new-title').value = '';
      document.getElementById('new-content').value = '';
      searchMemories();
      loadAudit();
    }

    async function submitUnlock() {
      const pin = document.getElementById('unlock-pin').value;
      const res = await fetch('/api/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin })
      });
      const data = await res.json();
      if (res.ok) {
        document.getElementById('unlock-pin').value = '';
        document.getElementById('lock-error').innerText = '';
        loadStatus();
        searchMemories();
        loadAudit();
      } else {
        document.getElementById('lock-error').innerText = data.error || 'Incorrect PIN.';
      }
    }

    async function lockVault() {
      await fetch('/api/lock', { method: 'POST' });
      loadStatus();
    }

    async function runDiskAudit() {
      const res = await fetch('/api/verify-disk');
      const data = await res.json();
      alert('On-Disk Encryption Audit Report:\n\n' + data.findings.map(f => '• ' + f).join('\n'));
    }

    async function rotateKey() {
      if (!confirm('Re-encrypt all database pages with a new 256-bit key via SQLCipher PRAGMA rekey?')) return;
      const res = await fetch('/api/rotate-key', { method: 'POST' });
      const data = await res.json();
      alert(data.message || 'Key rotation complete.');
      loadAudit();
    }

    async function loadAudit() {
      const res = await fetch('/api/audit');
      const data = await res.json();
      const tbody = document.getElementById('audit-tbody');
      tbody.innerHTML = '';
      data.events.forEach(ev => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="color: var(--text-muted);">${ev.timestamp.replace('T', ' ').substring(0, 19)}</td>
          <td><span class="badge" style="background:#1E293B; color:#38BDF8;">${ev.event_type}</span></td>
          <td>${ev.actor_id || 'system'}</td>
          <td>${ev.module || ''} / ${ev.action || ''}</td>
          <td style="font-family: monospace; font-size: 12px; color:#94A3B8;">${ev.details_json}</td>
        `;
        tbody.appendChild(tr);
      });
    }

    function switchTab(name) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.getElementById('tab-storage').style.display = name === 'storage' ? 'block' : 'none';
      document.getElementById('tab-audit').style.display = name === 'audit' ? 'block' : 'none';
      event.target.classList.add('active');
      if (name === 'audit') loadAudit();
    }

    // Initial load
    loadStatus();
    searchMemories();
    setInterval(loadStatus, 3000);
  </script>
</body>
</html>
"""


class SecurityDashboardHandler(BaseHTTPRequestHandler):
    sec_mgr: SecurityManager

    def log_message(self, format, *args):
        # Clean logging
        pass

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/status":
            user = self.sec_mgr.auth.get_primary_user()
            bio_avail, bio_code, bio_desc = self.sec_mgr.auth.biometric_authenticator.is_biometric_available()
            self._send_json(200, {
                "cipher_version": self.sec_mgr.db.get_cipher_version(),
                "database_filename": self.sec_mgr.config.database_filename,
                "is_locked": self.sec_mgr.is_locked,
                "key_backend": self.sec_mgr.key_storage.__class__.__name__,
                "user": user.model_dump(mode="json") if user else None,
                "biometrics": {
                    "available": bio_avail,
                    "code": bio_code.value,
                    "desc": bio_desc,
                }
            })

        elif path == "/api/memories":
            query_params = urllib.parse.parse_qs(parsed.query)
            q = query_params.get("q", [""])[0]
            if self.sec_mgr.is_locked:
                self._send_json(403, {"error": "Vault is locked. Unlock to access records."})
                return
            memories = self.sec_mgr.storage.memories.search_memories(q)
            self._send_json(200, {"memories": [m.model_dump(mode="json") for m in memories]})

        elif path == "/api/audit":
            cur = self.sec_mgr.db.cursor()
            cur.execute("SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT 50;")
            rows = [dict(r) for r in cur.fetchall()]
            self._send_json(200, {"events": rows})

        elif path == "/api/verify-disk":
            is_secure, findings = self.sec_mgr.verify_disk_encryption()
            self._send_json(200, {"is_secure": is_secure, "findings": findings})

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(body) if body else {}

        if path == "/api/unlock":
            pin = payload.get("pin", "")
            user = self.sec_mgr.auth.get_primary_user()
            username = user.username if user else "owner"
            try:
                session = self.sec_mgr.unlock_with_pin(username, pin)
                self._send_json(200, {"status": "unlocked", "session_id": session.session_id})
            except (InvalidCredentialsError, PINLockedError) as e:
                self._send_json(401, {"error": str(e)})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        elif path == "/api/lock":
            self.sec_mgr.lock(reason="web_ui")
            self._send_json(200, {"status": "locked"})

        elif path == "/api/memories":
            if self.sec_mgr.is_locked:
                self._send_json(403, {"error": "Vault is locked."})
                return
            title = payload.get("title", "")
            content = payload.get("content", "")
            is_shared = payload.get("is_shared_with_caregiver", False)
            mem_id = self.sec_mgr.storage.memories.save_memory(MemoryRecord(
                title=title, content=content, is_shared_with_caregiver=is_shared
            ))
            self._send_json(201, {"id": mem_id})

        elif path == "/api/rotate-key":
            if self.sec_mgr.is_locked:
                self._send_json(403, {"error": "Vault is locked."})
                return
            self.sec_mgr.rotate_encryption_key()
            self._send_json(200, {"message": "Master key rotated and database re-keyed successfully via PRAGMA rekey."})

        else:
            self.send_error(404, "Not Found")


def run_web_dashboard(port: int = 8080):
    config = SecurityConfig()
    sec_mgr = SecurityManager(config)
    sec_mgr.initialize()

    # If first time, set up default user
    if not sec_mgr.auth.is_setup_completed():
        sec_mgr.auth.setup_initial_user(
            username="eleanor_vance",
            display_name="Eleanor Vance",
            pin="739104",
            confirm_pin="739104",
            enable_biometrics=True,
        )

    # Unlock initially so user immediately sees active state
    sec_mgr.unlock_with_pin("eleanor_vance", "739104")

    # Add sample memories if empty
    if len(sec_mgr.storage.memories.search_memories("")) == 0:
        sec_mgr.storage.memories.save_memory(MemoryRecord(
            title="Lisinopril Morning Schedule",
            content="Blood pressure medication taken daily at 8:00 AM with water and breakfast.",
            category="medical",
            is_shared_with_caregiver=True,
        ))
        sec_mgr.storage.memories.save_memory(MemoryRecord(
            title="Cedar Lake Nature Walk",
            content="Walked along the cedar lake boardwalk with Sarah. Saw wild ducklings near the pier.",
            category="places",
            is_shared_with_caregiver=False,
        ))

    SecurityDashboardHandler.sec_mgr = sec_mgr
    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, SecurityDashboardHandler)
    print("================================================================")
    print(f" SECURITY DASHBOARD RUNNING AT: http://127.0.0.1:{port}")
    print(" Default PIN: 739104")
    print("================================================================")
    try:
        httpd.serve_forever()
    finally:
        sec_mgr.shutdown()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_web_dashboard(port)
