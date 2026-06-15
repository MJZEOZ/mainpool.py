import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

# --- تنظیمات بازو ---
TOKEN = os.environ.get("BOT_TOKEN") 
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
REQUIRED_CHANNEL = "@wamsara"
CHANNEL_LINK = "https://ble.ir/wamsara"

def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS polls 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id TEXT, question TEXT, 
         options TEXT, votes TEXT, voters TEXT, img_id TEXT)''')
    conn.commit()
    conn.close()

init_db()
user_state = {}

def bot_api(method, data=None):
    try:
        return requests.post(f"{BASE_URL}/{method}", json=data, timeout=10)
    except:
        return None

def check_membership(user_id, chat_id=REQUIRED_CHANNEL):
    try:
        res = bot_api("getChatMember", {"chat_id": chat_id, "user_id": int(user_id)})
        if res and res.status_code == 200:
            status = res.json().get("result", {}).get("status")
            return status in ["member", "administrator", "creator"]
    except: pass
    return False

def is_bot_admin(chat_id):
    # بررسی اینکه آیا بازو در کانال مقصد دسترسی دارد یا خیر
    try:
        res = bot_api("getChat", {"chat_id": chat_id})
        return res and res.status_code == 200
    except: return False

@app.route("/", methods=["GET", "POST"])
def receive_update():
    if request.method == "GET": return "PollFarsiBot is Online", 200
    update = request.get_json(silent=True)
    if not update: return "ok", 200

    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        user_id = str(msg["from"]["id"])
        text = msg.get("text", "")

        if text == "/start":
            user_state[user_id] = None
            bot_api("sendMessage", {
                "chat_id": chat_id, 
                "text": "🌟 به ربات نظرسنجی خوش آمدید.\nیکی از گزینه‌ها را انتخاب کنید:",
                "reply_markup": {"keyboard": [[{"text": "🚀 ساخت نظرسنجی جدید"}], [{"text": "📊 نظرسنجی‌های من"}]], "resize_keyboard": True}
            })
        elif text == "🚀 ساخت نظرسنجی جدید":
            user_state[user_id] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {"chat_id": chat_id, "text": "🔴 سوال نظرسنجی را بفرستید:", "reply_markup": {"remove_keyboard": True}})
        elif text == "📊 نظرسنجی‌های من":
            show_my_polls(chat_id, user_id)
        elif user_id in user_state and user_state[user_id]:
            handle_steps(chat_id, user_id, msg)

    elif "callback_query" in update:
        handle_callbacks(update["callback_query"])

    return "ok", 200

def handle_steps(chat_id, user_id, msg):
    state = user_state[user_id]
    text = msg.get("text", "")

    if state["step"] == "get_q":
        state.update({"q": text, "step": "get_opts"})
        bot_api("sendMessage", {"chat_id": chat_id, "text": "🟢 سوال ثبت شد. حالا گزینه‌ها را یکی‌یکی بفرستید:", "reply_markup": {"inline_keyboard": [[{"text": "✅ تایید نهایی گزینه‌ها", "callback_data": "finish_opts"}]]}})
    
    elif state["step"] == "get_opts" and text:
        state["opts"].append(text)
        bot_api("sendMessage", {"chat_id": chat_id, "text": f"گزینه '{text}' اضافه شد. گزینه بعدی؟", "reply_markup": {"inline_keyboard": [[{"text": "✅ تایید نهایی گزینه‌ها", "callback_data": "finish_opts"}]]}})

    elif state["step"] == "get_img" and "photo" in msg:
        img_id = msg["photo"][-1]["file_id"]
        save_poll(user_id, state["q"], state["opts"], img_id)
        user_state[user_id] = None
        bot_api("sendMessage", {"chat_id": chat_id, "text": "✅ نظرسنجی تصویری ساخته شد."})
        show_my_polls(, user_id)

    elif state["step"] == "get_pub_channel":
        if not text.startswith("@"):
            bot_api("sendMessage", {"chat_id": chat_id, "text": "⚠️ آیدی کانال باید با @ شروع شود. دوباره بفرستید:"})
            return
        
        # مرحله بررسی ادمین بودن بازو در کانال مقصد
        bot_api("sendMessage", {"chat_id": chat_id, "text": f"⏳ در حال بررسی دسترسی بازو به کانال {text}..."})
        if is_bot_admin(text):
            publish_now(chat_id, user_id, text, state["p_id"])
            user_state[user_id] = None
        else:
            bot_api("sendMessage", {
                "chat_id": chat_id, 
                "text": f"❌ خطای دسترسی!\n\nبازو هنوز در کانال {text} ادمین نشده است.\n\nلطفاً ابتدا بازو را در کانال خود ادمین کرده و سپس دوباره آیدی کانال را بفرستید:"
            })

def save_poll(creator_id, q, opts, img_id=None):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO polls (creator_id, question, options, votes, voters, img_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (creator_id, q, json.dumps(opts), json.dumps([0]*len(opts)), "[]", img_id))
    conn.commit()
    conn.close()

def show_my_polls(chat_id, user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, question FROM polls WHERE creator_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        bot_
