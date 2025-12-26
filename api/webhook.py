import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

TOKEN = os.environ.get("TELEGRAM_TOKEN")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # читаем json от Telegram
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length)

        try:
            update = json.loads(body.decode("utf-8"))
        except Exception:
            self._ok()
            return

        message = update.get("message") or {}
        chat = message.get("chat", {}) or {}
        chat_id = chat.get("id")

        if chat_id and TOKEN:
            payload = json.dumps({
                "chat_id": chat_id,
                "text": "Привет",
            }).encode("utf-8")

            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

        self._ok()

    def do_GET(self):
        self._ok()

    def _ok(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
