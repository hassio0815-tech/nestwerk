"""Lokaler Fake-HTTP-Server für Adapter-Tests (nur 127.0.0.1, keine echten Netzaufrufe)."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeServer:
    def __init__(self):
        self.antworten = []  # Liste von (status, body_dict_oder_str, verzoegerung, header)
        self.anfragen = []  # (pfad, header_dict, body_dict)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                laenge = int(self.headers.get("Content-Length", 0))
                roh = self.rfile.read(laenge)
                outer.anfragen.append(
                    (self.path, {k.lower(): v for k, v in self.headers.items()}, json.loads(roh))
                )
                status, body, verzoegerung, header = outer.antworten.pop(0)
                if verzoegerung:
                    time.sleep(verzoegerung)
                daten = body if isinstance(body, str) else json.dumps(body)
                try:
                    self.send_response(status)
                    for k, v in header.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(daten.encode())))
                    self.end_headers()
                    self.wfile.write(daten.encode())
                except OSError:
                    pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )

    def antwort(self, body, status=200, verzoegerung=0, header=None):
        self.antworten.append((status, body, verzoegerung, header or {}))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def openai_antwort(text="OK", ein=11, aus=3):
    return {
        "choices": [{"message": {"role": "assistant", "content": text}}],
        "usage": {"prompt_tokens": ein, "completion_tokens": aus},
    }


def anthropic_antwort(text="OK", ein=11, aus=3):
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": ein, "output_tokens": aus},
    }
