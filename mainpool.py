import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

# --- CONFIG ---
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
    except:
        return None

def check_membership(user_id):
    try:
        res = bot_api("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": int(user_id)})
        if res and res.status_code == 200:
            status = res.json().get("result", {}).get("status")
            return status in ["member", "administrator", "creator"]
    except: pass
    return False

def is_bot_admin(chat_id):
    try:
        res = bot_api("getChat", {"chat_id": chat_id})
        return res and res.status_code == 200
    except: return False

def show_my_polls(chat_id, user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, question FROM polls WHERE creator_id=?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        bot_api("sendMessage", {"chat_id": chat_id, "text": "Shoma hanooz nazarsanji nasakhteid."})
        return
    btns = [[{"text": f"Poll: {r[1][:20]}", "callback_data": f"rep_{r[0]}"}] for r in rows]
    bot_api("sendMessage", {"chat_id": chat_id, "text": "List nazarsanji haye shoma:", "reply_markup": {"inline_keyboard": btns}})

def save_poll(creator_id, q, opts, img_id=None):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO polls (creator_id, question, options, votes, voters, img_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (creator_id, q, json.dumps(opts), json.dumps([0]*len(opts)), "[]", img_id))
    conn.commit()
    conn.close()

def handle_steps(chat_id, user_id, msg):
    state = user_state.get(user_id)
    if not state: return
    text = msg.get("text", "")

    if state["step"] == "get_q" and text:
        state["q"] = text
        state["step"] = "get_opts"
        bot_api("sendMessage", {"chat_id": chat_id, "text": "Soal sabt shod. Hala gozineha ra yeki yeki befrestid:", "reply_markup": {"inline_keyboard": [[{"text": "Tayid Nahaee Gozineha", "callback_data": "finish_opts"}]]}})
    
    elif state["step"] == "get_opts" and text:
        state["opts"].append(text)
        bot_api("sendMessage", {"chat_id": chat_id, "text": f"Gozine '{text}' ezafe shod. Baadi?", "reply_markup": {"inline_keyboard": [[{"text": "Tayid Nahaee Gozineha", "callback_data": "finish_opts"}]]}})

    elif state["step"] == "get_img" and "photo" in msg:
        img_id = msg["photo"][-1]["file_id"]
        save_poll(user_id, state["q"], state["opts"], img_id)
        user_state[user_id] = None
        bot_api("sendMessage", {"chat_id
