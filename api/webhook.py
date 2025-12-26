import json
import os
import urllib.request

BOT_TOKEN = os.environ["BOT_TOKEN"]

def handler(request, response):
    if request.method != "POST":
        # чтобы не было 501 на GET
        response.status_code = 200
        response.text = "ok"
        return response

    data = json.loads(request.body.decode("utf-8"))
    print("TG update:", data)

    message = data.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if chat_id:
        if text == "/start":
            reply = "Привет! Это тестовый ответ на /start из Vercel‑бота."
        else:
            reply = f"Ты написал: {text}"

        payload = json.dumps({
            "chat_id": chat_id,
            "text": reply
        }).encode("utf-8")

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req)  # если здесь будет ошибка, её увидишь в логах Vercel

    response.status_code = 200
    response.text = "ok"
    return response
