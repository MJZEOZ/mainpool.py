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
    btns = [[{"text": "Poll: " + str(r[1][:20]), "callback_data": "rep_" + str(r[0])}] for r in rows]
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
        kb = {"inline_keyboard": [[{"text": "Finish Options", "callback_data": "finish_opts"}]]}
        bot_api("sendMessage", {"chat_id": chat_id, "text": "Soal sabt shod. Gozineha ra befrestid:", "reply_markup": kb})
    
    elif state["step"] == "get_opts" and text:
        state["opts"].append(text)
        kb = {"inline_keyboard": [[{"text": "Finish Options", "callback_data": "finish_opts"}]]}
        bot_api("sendMessage", {"chat_id": chat_id, "text": "Gozine sabt shod. Baadi?", "reply_markup": kb})

    elif state["step"] == "get_img" and "photo" in msg:
        img_id = msg["photo"][-1]["file_id"]
        save_poll(user_id, state["q"], state["opts"], img_id)
        user_state[user_id] = None
        bot_api("sendMessage", {"chat_id": chat_id, "text": "Nazarsanji tasviri sakhte shod."})
        show_my_polls(chat_id, user_id)

    elif state["step"] == "get_pub_channel" and text:
        if not text.startswith("@"):
            bot_api("sendMessage", {"chat_id": chat_id, "text": "ID bayad ba @ shoru shavad."})
        else:
            bot_api("sendMessage", {"chat_id": chat_id, "text": "Checking..."})
            if is_bot_admin(text):
                publish_now(chat_id, user_id, text, state["p_id"])
                user_state[user_id] = None
            else:
                bot_api("sendMessage", {"chat_id": chat_id, "text": "Bot is not admin in that channel!"})

def publish_now(chat_id, user_id, dest_channel, p_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, img_id FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        q, opts, img = row[0], json.loads(row[1]), row[2]
        kb = [[{"text": o, "callback_data": "v_" + str(p_id) + "_" + str(i)}] for i, o in enumerate(opts)]
        if img: 
            bot_api("sendPhoto", {"chat_id": dest_channel, "photo": img, "caption": q, "reply_markup": {"inline_keyboard": kb}})
        else: 
            bot_api("sendMessage", {"chat_id": dest_channel, "text": q, "reply_markup": {"inline_keyboard": kb}})
        bot_api("sendMessage", {"chat_id": chat_id, "text": "Published successfully."})

@app.route("/", methods=["GET", "POST"])
def receive_update():
    if request.method == "GET": return "Online", 200
    update = request.get_json(silent=True)
    if not update: return "ok", 200
    if "message" in update:
        m = update["message"]
        cid, uid = m["chat"]["id"], str(m["from"]["id"])
        txt = m.get("text", "")
        if txt == "/start":
            user_state[uid] = None
            kb = {"keyboard": [[{"text": "Create"}], [{"text": "My Polls"}]], "resize_keyboard": True}
            bot_api("sendMessage", {"chat_id": cid, "text": "Welcome:", "reply_markup": kb})
        elif txt == "Create":
            user_state[uid] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {"chat_id": cid, "text": "Send Question:", "reply_markup": {"remove_keyboard": True}})
        elif txt == "My Polls":
            show_my_polls(cid, uid)
        elif uid in user_state and user_state[uid]:
            handle_steps(cid, uid, m)
    elif "callback_query" in update:
        handle_callbacks(update["callback_query"])
    return "ok", 200

def handle_callbacks(cq):
    uid, cid, data = str(cq["from"]["id"]), cq["message"]["chat"]["id"], cq["data"]
    if data == "finish_opts":
        state = user_state.get(uid, {})
        if len(state.get("opts", [])) < 2:
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Min 2 options!", "show_alert": True})
        else:
            state["step"] = "get_img"
            kb = {"inline_keyboard": [[{"text": "No Photo", "callback_data": "skip_img"}]]}
            bot_api("sendMessage", {"chat_id": cid, "text": "Send photo or skip:", "reply_markup": kb})
    elif data == "skip_img":
        s = user_state.get(uid)
        if s:
            save_poll(uid, s["q"], s["opts"])
            user_state[uid] = None
            bot_api("sendMessage", {"chat_id": cid, "text": "Saved."})
            show_my_polls(cid, uid)
    elif data.startswith("rep_"):
        show_report(cid, uid, data.split("_")[1])
    elif data.startswith("del_"):
        conn = sqlite3.connect('bot_data.db')
        conn.cursor().execute("DELETE FROM polls WHERE id=?", (data.split("_")[1],))
        conn.commit()
        conn.close()
        bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Deleted"})
        show_my_polls(cid, uid)
    elif data.startswith("pub_"):
        if not check_membership(uid):
            bot_api("sendMessage", {"chat_id": cid, "text": "Join channel: " + CHANNEL_LINK})
        else:
            user_state[uid] = {"step": "get_pub_channel", "p_id": data.split("_")[1]}
            bot_api("sendMessage", {"chat_id": cid, "text": "Send channel ID (e.g @test):"})
    elif data.startswith("v_"):
        process_vote(cid, uid, cq)

def show_report(cid, uid, p_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, votes, img_id FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        q, opts, v_list, img = row
