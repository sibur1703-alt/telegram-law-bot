import json
import os
import urllib.request
import urllib.error


BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")


def handler(request, response):
    # 1. Хелсчек и защита от GET
    if request.method != "POST":
        response.status_code = 200
        response.text = "ok"
        return response

    # 2. Проверяем, что токен вообще есть
    if not BOT_TOKEN:
        print("NO TELEGRAM_TOKEN in env!")
        response.status_code = 500
        response.text = "TELEGRAM_TOKEN is not set"
        return response

    # 3. Парсим апдейт от Telegram
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception as e:
        print("Bad JSON from Telegram:", repr(e))
        response.status_code = 200
        response.text = "ok"
        return response

    print("TG update:", data)

    message = data.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")

    if chat_id:
        if text == "/start":
            reply = (
                "Привет! Это тестовый ответ на /start из "
                "Vercel‑бота. Если ты это видишь — вебхук жив."
            )
        else:
            reply = f"Ты написал: {text}"

        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": reply,
                "parse_mode": "Markdown",
            }
        ).encode("utf-8")

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=20)
            body = resp.read()
            print("TG sendMessage status:", resp.status, body)
        except urllib.error.HTTPError as e:
            print("TG HTTPError:", e.code, e.read())
        except Exception as e:
            print("TG sendMessage error:", repr(e))

    # 4. Отвечаем Telegram, что всё ок
    response.status_code = 200
    response.text = "ok"
    return response
