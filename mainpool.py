import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

# --- CONFIG ---
TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = "https://tapi.bale.ai/bot" + str(TOKEN)
REQUIRED_CHANNEL = "@wamsara"
CHANNEL_LINK = "https://ble.ir/wamsara"

def init_db():
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS polls 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id TEXT, question TEXT, 
             options TEXT, votes TEXT, voters TEXT, img_id TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print("DB Error: " + str(e))

init_db()
user_state = {}

def bot_api(method, data=None):
    if not TOKEN:
        print("Error: BOT_TOKEN is missing in Environment Variables!")
        return None
    try:
        res = requests.post(BASE_URL + "/" + method, json=data, timeout=10)
        return res
    except:
        return None

def check_membership(uid):
    try:
        r = bot_api("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": int(uid)})
        if r and r.status_code == 200:
            s = r.json().get("result", {}).get("status")
            return s in ["member", "administrator", "creator"]
    except: pass
    return False

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return "Bot is running...", 200
    
    update = request.get_json(silent=True)
    if not update:
        return "ok", 200

    if "message" in update:
        msg = update["message"]
        cid = msg["chat"]["id"]
        uid = str(msg["from"]["id"])
        txt = msg.get("text", "")

        if txt == "/start":
            kb = {"keyboard": [[{"text": "Sakht Nazarsanji"}], [{"text": "My Polls"}]], "resize_keyboard": True}
            bot_api("sendMessage", {"chat_id": cid, "text": "Welcome to Poll Bot:", "reply_markup": kb})
        
        elif txt == "Sakht Nazarsanji":
            user_state[uid] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {"chat_id": cid, "text": "Send Question:", "reply_markup": {"remove_keyboard": True}})
            
        elif uid in user_state and user_state[uid]:
            state = user_state[uid]
            if state["step"] == "get_q":
                state["q"] = txt
                state["step"] = "get_opts"
                bot_api("sendMessage", {"chat_id": cid, "text": "Question saved. Send options one by one. Press button when done.", "reply_markup": {"inline_keyboard": [[{"text": "Finish", "callback_data": "finish"}]]}})
            elif state["step"] == "get_opts":
                state["opts"].append(txt)
                bot_api("sendMessage", {"chat_id": cid, "text": "Added. Next?", "reply_markup": {"inline_keyboard": [[{"text": "Finish", "callback_data": "finish"}]]}})

    elif "callback_query" in update:
        cq = update["callback_query"]
        uid = str(cq["from"]["id"])
        cid = cq["message"]["chat"]["id"]
        data = cq["data"]
        
        if data == "finish":
            state = user_state.get(uid)
            if state and len(state["opts"]) >= 2:
                # Save to DB
                conn = sqlite3.connect('bot_data.db')
                cursor = conn.cursor()
                cursor.execute("INSERT INTO polls (creator_id, question, options, votes, voters) VALUES (?, ?, ?, ?, ?)",
                               (uid, state["q"], json.dumps(state["opts"]), json.dumps([0]*len(state["opts"])), "[]"))
                conn.commit()
                conn.close()
                user_state[uid] = None
                bot_api("sendMessage", {"chat_id": cid, "text": "Poll saved successfully!"})
            else:
                bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Need at least 2 options!"})

    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
