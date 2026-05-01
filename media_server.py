# ═══════════════════════════════════════════════════════════
#  media_server.py  –  Eigenständiger Medien-Dateiserver
#  Läuft als separater Prozess, KEIN Eventlet
#  Port 5001 – unterstützt Range-Requests nativ
# ═══════════════════════════════════════════════════════════

import sys
import os
import http.server

def run(directory, port=5001):
    class MediaHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt, *args):
            pass  # Logs unterdrücken

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

    server = http.server.HTTPServer(("0.0.0.0", port), MediaHandler)
    print(f"[MediaServer] Läuft auf Port {port} → {directory}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    port      = int(sys.argv[2]) if len(sys.argv) > 2 else 5001
    run(directory, port)
