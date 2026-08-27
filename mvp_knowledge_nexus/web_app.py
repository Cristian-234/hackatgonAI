import importlib
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import knowledge_nexus


WEB_DIR = APP_DIR / "web"


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(WEB_DIR / "index.html")
            return
        if parsed.path == "/api/needs":
            self.send_json({"needs": knowledge_nexus.available_needs()})
            return
        if parsed.path == "/api/connect":
            query = parse_qs(parsed.query)
            need_id = query.get("need", ["NEED-001"])[0]
            top = int(query.get("top", ["12"])[0])
            balanced = query.get("mode", ["balanced"])[0] != "ranking"
            try:
                payload = knowledge_nexus.connect_need(need_id, top_k=top, balanced=balanced)
                self.send_json(payload)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.send_json({"error": str(exc)}, status=500)
            return
        if parsed.path == "/api/query":
            query = parse_qs(parsed.query)
            query_text = query.get("q", [""])[0]
            top = int(query.get("top", ["12"])[0])
            balanced = query.get("mode", ["balanced"])[0] != "ranking"
            try:
                payload = knowledge_nexus.connect_custom_query(query_text, top_k=top, balanced=balanced)
                self.send_json(payload)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.send_json({"error": str(exc)}, status=500)
            return
        if parsed.path == "/api/benchmark":
            try:
                payload = knowledge_nexus.run_benchmark()
                self.send_json(payload)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.send_json({"error": str(exc)}, status=500)
            return
        if parsed.path.startswith("/web/"):
            requested = WEB_DIR / parsed.path.removeprefix("/web/")
            self.serve_file(requested)
            return
        self.send_json({"error": "Ruta no encontrada"}, status=404)

    def serve_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not str(resolved).startswith(str(WEB_DIR.resolve())) or not resolved.exists():
            self.send_json({"error": "Archivo no encontrado"}, status=404)
            return
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    print("[1/2] Indexando entidades y precargando base de conocimiento en memoria...")
    kb = knowledge_nexus.get_knowledge_base()
    print(f"[2/2] {len(kb['entities'])} entidades indexadas con éxito. Servidor listo.")
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Knowledge Nexus dashboard listo en http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
