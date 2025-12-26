import os
import re
import json
import urllib.request
from http.server import BaseHTTPRequestHandler
from groq import Groq


# ---- Конфиг ----

BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "..", "data", "duma_bills_links_FULL.json")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
LOG_GROUP_ID = -1003520936452


# ---- Загрузка базы ----

try:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        BILLS = json.load(f)
except Exception:
    BILLS = []


BILL_RE = re.compile(r"(\d{5,}-\d+)")


# ---- Утилиты ----

def clean_telegram_formatting(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'~(.*?)~', r'\1', text)
    text = re.sub(r'\|\|(.*?)\|\|', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    return text


def normalize_bill_number(text: str) -> str | None:
    if not text:
        return None
    text = clean_telegram_formatting(text)
    text = text.replace("№", " ")
    text = text.replace("#", " ")
    text = text.strip()

    if "sozd.duma.gov.ru/bill/" in text:
        part = text.split("sozd.duma.gov.ru/bill/")[-1]
        m = BILL_RE.search(part)
        if m:
            return m.group(1)

    m = BILL_RE.search(text)
    if m:
        return m.group(1)
    return None


def find_bill(text: str):
    bill_number = normalize_bill_number(text)
    if not bill_number or not BILLS:
        return None, None, None

    bill_number_str = str(bill_number)

    for row in BILLS:
        row_number = (
            row.get("bill_number")
            or row.get("number")
            or row.get("billId")
        )
        if row_number and str(row_number) == bill_number_str:
            url = (
                row.get("url")
                or row.get("link")
                or f"https://sozd.duma.gov.ru/bill/{bill_number_str}"
            )
            return bill_number_str, url, row

    return bill_number_str, None, None


def get_bill_row_by_number(bill_number: str) -> dict | None:
    if not BILLS:
        return None
    for row in BILLS:
        row_number = (
            row.get("bill_number")
            or row.get("number")
            or row.get("billId")
        )
        if row_number and str(row_number) == str(bill_number):
            return row
    return None


def clean_title(title: str) -> str:
    if not title:
        return ""
    title = title.replace("\u00a0", " ")
    title = "".join(ch for ch in title if ch.isprintable())
    return title.strip()


def format_date(date_str: str) -> str:
    """
    Пытается привести дату к формату DD.MM.YYYY.
    Если дата в формате YYYY-MM-DD или ISO, переворачиваем.
    """
    if not date_str:
        return ""
    
    date_str = date_str.strip()
    
    # если уже DD.MM.YYYY
    if re.match(r'\d{2}\.\d{2}\.\d{4}', date_str):
        return date_str
    
    # если YYYY-MM-DD или похожее
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if m:
        year, month, day = m.groups()
        return f"{day}.{month}.{year}"
    
    return date_str


def get_bill_date(row: dict) -> str:
    """
    Ищет дату регистрации/публикации закона в JSON.
    Возвращает отформатированную дату или пустую строку.
    """
    date_fields = [
        "registration_date",
        "date",
        "published_date",
        "introductionDate",
        "created_date",
    ]
    
    for field in date_fields:
        date_val = row.get(field)
        if date_val:
            return format_date(str(date_val))
    
    return ""


def make_short_info(row: dict, max_len: int = 200) -> str:
    """
    Нормальное название + укороченное описание.
    """
    title = clean_title(row.get("title") or "")
    desc = (row.get("description") or "").strip()

    for bad_tail in ("в архиве", "в архиве.", "в архиве", "в архиве."):
        if title.lower().endswith(bad_tail):
            title = title[: -len(bad_tail)].rstrip(" ,.-")

    base = title or "(без названия)"

    if desc:
        desc_clean = " ".join(desc.split())
        if len(desc_clean) > max_len:
            desc_clean = desc_clean[:max_len].rsplit(" ", 1)[0] + "…"
        return f"{base} — {desc_clean}"

    return base


def search_bills(query: str, limit: int = 10):
    if not query or not BILLS:
        return []

    q = query.lower().strip()
    if BILL_RE.search(q):
        return []

    results: list[dict] = []

    for row in BILLS:
        title = (row.get("title") or "").lower()
        desc = (row.get("description") or "").lower()

        if q in title or q in desc:
            results.append(row)
            if len(results) >= limit:
                break

    return results


# ---- Промт ----

USER_PROMPT_TEMPLATE = """
Ты — объяснительный ИИ, который рассказывает о законах простыми словами, с юмором и примерами из жизни 😊

Твоя задача — объяснить законопроект так, чтобы человек без юридического образования понял, зачем он нужен и как это его касается.
""".strip()


# ---- Groq ----

_groq_client = None


def get_groq_client():
    global _groq_client
    if _groq_client is None:
        if not GROQ_API_KEY:
            return None
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def build_bill_text(bill_number: str, bill_url: str, bill_row: dict | None) -> str:
    parts = [
        f"Номер законопроекта: {bill_number}",
        f"Ссылка: {bill_url}",
    ]

    if bill_row:
        title = (bill_row.get("title") or "").strip()
        description = (bill_row.get("description") or "").strip()

        if title:
            parts.append(f"\nНазвание:\n{title}")
        if description:
            parts.append(f"\nОписание:\n{description}")

    return "\n".join(parts)


def call_llama(prompt: str, bill_number: str) -> str:
    client = get_groq_client()
    if not client:
        return (
            "Не настроен GROQ_API_KEY. Добавь ключ Groq в переменные окружения "
            "проекта, чтобы я мог анализировать законопроекты."
        )

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты эксперт по российскому законодательству. "
                    "Работаешь с законопроектами Госдумы, номер вида 1052810-8. "
                    "Отвечай строго по предоставленному описанию законопроекта. "
                    "Не выдумывай деталей, которых нет в тексте."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.3,
        max_completion_tokens=1500,
    )

    answer = completion.choices[0].message.content.strip()
    header = f"📋 **Закон № {bill_number}**\n\n"
    return header + answer


# ---- Telegram ----

def send_telegram_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    if not TELEGRAM_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass


def answer_callback_query(callback_query_id: str) -> None:
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
    payload = json.dumps({"callback_query_id": callback_query_id}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception:
        pass


def send_to_log_group(user_label: str, chat_id: int, user_query: str, bot_reply: str) -> None:
    if not TELEGRAM_TOKEN or not LOG_GROUP_ID:
        return

    log_text = (
        f"📩 *Запрос от пользователя*\n"
        f"👤 {user_label} (chat_id: `{chat_id}`)\n"
        f"💬 Запрос:\n{user_query}\n\n"
        f"🤖 *Ответ бота:*\n{bot_reply}"
    )

    send_telegram_message(LOG_GROUP_ID, log_text)


# ---- Webhook handler ----

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length)

        try:
            update = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return

        # ---- callback_query от inline‑кнопок ----
        if "callback_query" in update:
            cq = update["callback_query"]
            data = cq.get("data") or ""
            chat = cq.get("message", {}).get("chat", {})
            chat_id = chat.get("id")
            callback_query_id = cq.get("id")

            if data.startswith("bill:") and chat_id:
                bill_number = data.split("bill:", 1)[1]
                row = get_bill_row_by_number(bill_number)
                url = f"https://sozd.duma.gov.ru/bill/{bill_number}"
                bill_text = build_bill_text(bill_number, url, row)
                full_prompt = f"{bill_text}\n\n{USER_PROMPT_TEMPLATE}"
                reply_text = call_llama(full_prompt, bill_number)
                send_telegram_message(chat_id, reply_text)
                if callback_query_id:
                    answer_callback_query(callback_query_id)

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return

        # ---- обычное сообщение ----
        message = update.get("message") or update.get("edited_message")
        if not message:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "") or ""

        user = message.get("from", {})
        username = user.get("username") or ""
        first_name = user.get("first_name") or ""
        last_name = user.get("last_name") or ""

        user_label_parts = []
        if username:
            user_label_parts.append(f"@{username}")
        if first_name or last_name:
            user_label_parts.append(f"{first_name} {last_name}".strip())
        user_label = " ".join(user_label_parts) or str(chat_id)

        if ADMIN_ID and chat_id != ADMIN_ID:
            admin_text = (
                f"Новый запрос к боту:\n"
                f"Пользователь: {user_label}\n"
                f"chat_id: {chat_id}\n"
                f"Текст: {text}"
            )
            send_telegram_message(ADMIN_ID, admin_text)

        # ---- команды ----

        if text.startswith("/start"):
            reply_text = (
                "Привет! Я объясняю законопроекты Госдумы простым языком.\n\n"
                "Что я умею:\n"
                "• Пришли номер законопроекта: 1052810-8 "
                "(список законопроектов смотри на sozd.duma.gov.ru)\n"
                "• Или пришли слово по теме, например: \"сво\" или \"китай\" — "
                "я подберу подходящие законопроекты по теме.\n"
            )
            send_telegram_message(chat_id, reply_text)

        elif text.startswith("/help"):
            reply_text = (
                "Как пользоваться ботом:\n\n"
                "1) Пришли номер законопроекта: 1052810-8 (можно с № или #).\n"
                "2) Или напиши несколько слов по теме — я подберу варианты.\n"
            )
            send_telegram_message(chat_id, reply_text)

        elif text.startswith("/about"):
            reply_text = (
                "У меня есть база законопроектов Госдумы: номер, ссылка, название и описание.\n"
                "Я нахожу нужный законопроект и прошу ИИ объяснить его простым языком.\n"
            )
            send_telegram_message(chat_id, reply_text)

        else:
            bill_number, bill_url, bill_row = find_bill(text)

            if bill_number:
                if not bill_url:
                    reply_text = (
                        f"Нашёл номер {bill_number}, но в базе его нет 😕\n"
                        "Возможно, JSON устарел или этот законопроект ещё не добавлен."
                    )
                    send_telegram_message(chat_id, reply_text)
                else:
                    bill_text = build_bill_text(bill_number, bill_url, bill_row)
                    full_prompt = f"{bill_text}\n\n{USER_PROMPT_TEMPLATE}"
                    reply_text = call_llama(full_prompt, bill_number)
                    send_telegram_message(chat_id, reply_text)
            else:
                rows = search_bills(text, limit=10)
                if not rows:
                    reply_text = (
                        "Не смог распознать номер законопроекта и ничего не нашёл по этому запросу 🤷‍♂️\n"
                        "Попробуй убрать окончание слова, например не полиция,а полиц, так мы расширим поиск."
                    )
                    send_telegram_message(chat_id, reply_text)
                else:
                    # сообщение‑заглушка
                    wait_text = (
                        "Секунду, подбираю подходящие законопроекты… "
                        "список появится ниже в течение 10–15 секунд 🙂"
                    )
                    send_telegram_message(chat_id, wait_text)

                    # одно сообщение + одна кнопка на каждый законопроект
                    for row in rows:
                        bill_num = (
                            row.get("bill_number")
                            or row.get("number")
                            or row.get("billId")
                            or "—"
                        )
                        bill_num_str = str(bill_num)
                        short_info = make_short_info(row)
                        bill_date = get_bill_date(row)

                        msg_text = f"• {short_info}"

                        # формируем текст кнопки с датой
                        if bill_date:
                            button_text = f"Расшифровать № {bill_num_str} (опубликован {bill_date})"
                        else:
                            button_text = f"Расшифровать № {bill_num_str}"

                        reply_markup = {
                            "inline_keyboard": [[
                                {
                                    "text": button_text,
                                    "callback_data": f"bill:{bill_num_str}",
                                }
                            ]]
                        }

                        send_telegram_message(chat_id, msg_text, reply_markup)

        send_to_log_group(user_label, chat_id, text, "ok")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
