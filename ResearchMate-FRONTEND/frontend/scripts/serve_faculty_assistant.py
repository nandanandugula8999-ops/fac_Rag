"""Serve the separate plain HTML/CSS/JS assistant; expose only the public API URL."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'integration' / 'faculty-assistant'

def configured_base_url():
    value = os.environ.get('VITE_API_BASE_URL')
    if not value:
        env_path = PUBLIC / '.env'
        if not env_path.is_file():
            env_path = PUBLIC / '.env.example'
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if line.strip().startswith('VITE_API_BASE_URL='):
                value = line.split('=', 1)[1].strip().strip('\"\'')
    parsed = urlsplit(value or '')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit('Set VITE_API_BASE_URL to an HTTP(S) FastAPI base URL without credentials.')
    return value.rstrip('/')

class Handler(SimpleHTTPRequestHandler):
    api_base_url = ''
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/config.js':
            body = ('window.FACULTY_CONFIG = ' + json.dumps({'apiBaseUrl': self.api_base_url}) + ';\n').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path in ('/', '/index.html', '/styles.css', '/app.js', '/api.js'):
            super().do_GET()
        else:
            self.send_error(404)
    def do_HEAD(self):
        if urlsplit(self.path).path not in ('/', '/index.html', '/styles.css', '/app.js', '/api.js'):
            self.send_error(404)
        else:
            super().do_HEAD()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5174)
    args = parser.parse_args()
    Handler.api_base_url = configured_base_url()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(PUBLIC)))
    print(f'Faculty Assistant: http://localhost:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
