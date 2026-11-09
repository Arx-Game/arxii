"""Exercise the real reload probe against a host-validating HTTP server."""

import http.server
from pathlib import Path
import subprocess
import threading


def test_reload_probe_uses_configured_host():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Host"))
            self.send_response(200 if seen[-1] == "reload.example.test" else 400)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        template = (
            Path(__file__).resolve().parents[2]
            / "infra/ansible/roles/app_deploy/templates/arxii-reload.sh.j2"
        ).read_text()
        assert 'WEB_HOST="{{ caddy_web_fqdn }}"' in template
        function = template.split("server_answers() {", 1)[1].split("\n}", 1)[0]
        script = (
            f"SERVER_PORT={server.server_port}\n"
            "WEB_HOST=reload.example.test\n"
            "port_holders() { echo 'pid=123'; }\n"
            "server_answers() {" + function + "\n}\nserver_answers 123\n"
        )
        subprocess.run(["bash", "-c", script], check=True)
        assert seen == ["reload.example.test"]
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
