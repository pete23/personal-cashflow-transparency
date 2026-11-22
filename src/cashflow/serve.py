"""Serve the pivot UI and the classified transactions on localhost."""

import json
import socket
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from socketserver import TCPServer

from cashflow.pivot import pivot_rows

CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, transactions: Path, **kwargs):
        self.transactions = transactions
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/transactions.json":
            # Read on every request, so rerunning `cashflow classify` shows up on refresh.
            body = json.dumps(pivot_rows(json.loads(self.transactions.read_text()))).encode()
            return self._send(body, CONTENT_TYPES[".json"])
        static = resources.files("cashflow").joinpath("static")
        name = "index.html" if path == "/" else path.lstrip("/")
        # Only serve known static files: no "..", and nothing outside static/ or static/vendor/.
        parts = name.split("/")
        if ".." in parts or len(parts) > 2 or (len(parts) == 2 and parts[0] != "vendor"):
            return self.send_error(HTTPStatus.NOT_FOUND)
        target = static.joinpath(*parts)
        suffix = Path(name).suffix
        if suffix not in CONTENT_TYPES or not target.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        self._send(target.read_bytes(), CONTENT_TYPES[suffix])

    def _send(self, body: bytes, content_type: str):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # keep the terminal quiet


class LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind looks up the host's FQDN, a reverse DNS call that can hang
        # for half a minute; nothing here uses the name.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def make_server(transactions: Path, port: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    # Localhost by default: this serves personal financial data with no authentication.
    return LocalServer((host, port), partial(Handler, transactions=transactions))


def lan_address() -> str | None:
    """This machine's address on the local network, found without sending any traffic."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # a reserved documentation address; UDP connect sends nothing
            return probe.getsockname()[0]
        except OSError:
            return None
