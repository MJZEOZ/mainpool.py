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
        res = requests.post(f"{BASE_URL}/{method}", json=data, timeout=15)
        return res
    except Exception:
        return None

def check_membership(user_id):
    try:
        res = bot_api("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": int(user_id)})
        if res and res.status_code == 200:
            status = res.json().get("result", {}).get("status")
            return status in ["member", "administrator", "creator"]
    except Exception: 
        pass
    return False

def is_bot_admin(chat_id):
    try:
        res = bot_api("getChat", {"chat_id": chat_id})
        return res and res.status_code == 200
    except Exception: 
        return False

def show_my_polls(chat_id, user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, question FROM polls WHERE creator_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        bot_api("sendMessage", {"chat_id": chat_id, "text": "📭 شما هنوز نظرسنجی نساخته‌اید."})
        return
    btns = [[{"text": f"📋 {r[1][:25]}...", "callback_data": f"rep_{r[0]}"}] for r in rows]
    bot_api("sendMessage", {"chat_id": chat_id, "text": "📂 نظرسنجی مورد نظر را انتخاب کنید:", "reply_markup": {"inline_keyboard": btns}})

def save_poll(creator_id, q, opts, img_id=None):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO polls (creator_id, question, options, votes, voters, img_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (creator_id, q, json.dumps(opts), json.dumps([0]*len(opts)), "[]", img_id))
    conn.commit()
    conn.close()

def publish_now(chat_id, user_id, dest_channel, p_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, img_id FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        q, opts, img = row[0], json.loads(row[1]), row[2]
        kb = [[{"text": o, "callback_data": f"v_{p_id}_{i}"}] for i, o in enumerate(opts)]
        if img: 
            bot_api("sendPhoto", {"chat_id": dest_channel, "photo": img, "caption": q, "reply_markup": {"inline_keyboard": kb}})
        else: 
            bot_api("sendMessage", {"chat_id": dest_channel, "text": q, "reply_markup": {"inline_keyboard": kb}})
        bot_api("sendMessage", {"chat_id": chat_id, "text": f"✅ با موفقیت در کانال {dest_channel} منتشر شد."})

def handle_steps(chat_id, user_id, msg):
    state = user_state.get(user_id)
    if not state: return
    text = msg.get("text", "")

    if state["step"] == "get_q" and text:
        state.update({"q": text, "step": "get_opts"})
        bot_api("sendMessage", {"chat_id": chat_id, "text": "🟢 سوال ثبت شد. حالا گزینه‌ها را یکی‌یکی بفرستید:", "reply_mark {"inline_keyboard": [[{"text": "✅ تایید نهایی گزینه‌ها", "callback_data": "finish_opts"}]]}})
    
    elif state["step"] == "get_opts" and text:
        state["opts"].append(text)
        bot_api("sendMessage", {"chat_id": chat_id, "text": f"گزینه '{text}' اضافه شد. گزینه بعدی؟", "reply_markup": {"inline_keyboard": [[{"text": "✅ تایید نهایی گزینه‌ها", "callback_data": "finish_opts"}]]}})

    elif state["step"] == "get_img" and "photo" in msg:
        img_id = msg["photo"][-1]["file_id"]
        save_poll(user_id, state["q"], state["opts"], img_id)
        user_state[user_id] = None
        bot_api("sendMessage", {"chat_id": chat_id, "text": "✅ نظرسنجی تصویری ساخته شد."})
        show_my_polls(chat_id, user_id)

    elif state["step"] == "get_pub_channel" and text:
        if not text.startswith("@"):
            bot_api("sendMessage", {"chat_id": chat_id, "text": "⚠️ آیدی کانال باید با @ شروع شود (مثلاً @wams
