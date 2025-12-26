# webhook.py
import json
import os
import urllib.request

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")

def handler(request, response):
    if request.method != "POST":
        response.status_code = 200
        response.text = "ok"
        return response

    if not BOT_TOKEN:
        response.status_code = 500
        response.text = "TELEGRAM_TOKEN is not set"
        return response

    data = json.loads(request.body.decode("utf-8"))
    print("TG update:", data)

    message = data.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if chat_id:
        reply = "Привет! Это тестовый ответ на /start из Vercel‑бота." if text == "/start" else f"Ты написал: {text}"
        payload = json.dumps({"chat_id": chat_id, "text": reply}).encode("utf-8")

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=20)

    response.status_code = 200
    response.text = "ok"
    return response
