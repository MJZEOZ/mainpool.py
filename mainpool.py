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

def check_membership(user_id):
    try:
        res = bot_api("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": int(user_id)})
        if res and res.status_code == 200:
            status = res.json().get("result", {}).get("status")
            return status in ["member", "administrator", "creator"]
    except: pass
    return False

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
                "text": "🌟 خوش آمدید.\nیکی از گزینه‌ها را انتخاب کنید:",
                "reply_markup": {
                    "keyboard": [[{"text": "🚀 ساخت نظرسنجی جدید"}], [{"text": "📊 نظرسنجی‌های من"}]],
                    "resize_keyboard": True
                }
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
        bot_api("sendMessage", {
            "chat_id": chat_id, 
            "text": "🟢 سوال ثبت شد. حالا گزینه‌ها را یکی‌یکی بفرستید:", 
            "reply_markup": {"inline_keyboard": [[{"text": "✅ تایید نهایی گزینه‌ها", "callback_data": "finish_opts"}]]}
        })
    
    elif state["step"] == "get_opts" and text:
        state["opts"].append(text)
        bot_api("sendMessage", {
            "chat_id": chat_id, 
            "text": f"گزینه '{text}' اضافه شد. گزینه بعدی؟", 
            "reply_markup": {"inline_keyboard": [[{"text": "✅ تایید نهایی گزینه‌ها", "callback_data": "finish_opts"}]]}
        })

    elif state["step"] == "get_img" and "photo" in msg:
        img_id = msg["photo"][-1]["file_id"]
        save_poll(user_id, state["q"], state["opts"], img_id)
        user_state[user_id] = None
        bot_api("sendMessage", {"chat_id": chat_id, "text": "✅ نظرسنجی تصویری ساخته شد."})
        show_my_polls(chat_id, user_id)

    elif state["step"] == "get_pub_channel":
        publish_now(chat_id, user_id, text, state["p_id"])

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
        bot_api("sendMessage", {"chat_id": chat_id, "text": "📭 لیست خالی است."})
        return
    btns = [[{"text": f"📋 {r[1][:20]}", "callback_data": f"rep_{r[0]}"}] for r in rows]
    bot_api("sendMessage", {"chat_id": chat_id, "text": "📂 نظرسنجی‌های شما:", "reply_markup": {"inline_keyboard": btns}})

def handle_callbacks(cq):
    user_id = str(cq["from"]["id"])
    chat_id = cq["message"]["chat"]["id"]
    data = cq["data"]

    if data == "finish_opts":
        if len(user_state.get(user_id, {}).get("opts", [])) < 2:
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "حداقل ۲ گزینه!", "show_alert": True})
        else:
            user_state[user_id]["step"] = "get_img"
            bot_api("sendMessage", {
                "chat_id": chat_id, 
                "text": "📸 تصویر بفرستید یا رد کنید:", 
                "reply_markup": {"inline_keyboard": [[{"text": "⏩ بدون تصویر", "callback_data": "skip_img"}]]}
            })

    elif data == "skip_img":
        state = user_state[user_id]
        save_poll(user_id, state["q"], state["opts"])
        user_state[user_id] = None
        bot_api("sendMessage", {"chat_id": chat_id, "text": "✅ ذخیره شد."})
        show_my_polls(chat_id, user_id)

    elif data.startswith("rep_"):
        show_report(chat_id, user_id, data.split("_")[1])

    elif data.startswith("del_"):
        conn = sqlite3.connect('bot_data.db')
        conn.cursor().execute("DELETE FROM polls WHERE id=?", (data.split("_")[1],))
        conn.commit()
        conn.close()
        show_my_polls(chat_id, user_id)

    elif data.startswith("pub_"):
        if not check_membership(user_id):
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": f"باید عضو {REQUIRED_CHANNEL} باشید", "show_alert": True})
        else:
            user_state[user_id] = {"step": "get_pub_channel", "p_id": data.split("_")[1]}
            bot_api("sendMessage", {"chat_id": chat_id, "text": "📢 آیدی کانال (با @):"})

    elif data.startswith("v_"):
        process_vote(chat_id, user_id, cq)

def show_report(chat_id, user_id, p_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, votes, img_id FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        q, opts, votes, img = row[0], json.loads(row[1]), json.loads(row[2]), row[3]
        total = sum(votes)
        report = f"📊 {q}\n\n"
        for i, o in enumerate(opts):
            p = (votes[i]/total*100) if total > 0 else 0
            report += f"{o}: {int(p)}% ({votes[i]})\n"
        
        btns = [
            [{"text": "🚀 انتشار در کانال", "callback_data": f"pub_{p_id}"}],
            [{"text": "🔄 بروزرسانی", "callback_data": f"rep_{p_id}"}, {"text": "🗑 حذف", "callback_data": f"del_{p_id}"}]
        ]
        if img:
            bot_api("sendPhoto", {"chat_id": chat_id, "photo": img, "caption": report, "reply_markup": {"inline_keyboard": btns}})
        else:
            bot_api("sendMessage", {"chat_id": chat_id, "text": report, "reply_markup": {"inline_keyboard": btns}})

def publish_now(chat_id, user_id, channel_id, p_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, img_id FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        q, opts, img = row[0], json.loads(row[1]), row[2]
        kb = [[{"text": o, "callback_data": f"v_{p_id}_{i}"}] for i, o in enumerate(opts)]
        if img:
            bot_api("sendPhoto", {"chat_id": channel_id, "photo": img, "caption": q, "reply_markup": {"inline_keyboard": kb}})
        else:
            bot_api("sendMessage", {"chat_id": channel_id, "text": q, "reply_markup": {"inline_keyboard": kb}})
        bot_api("sendMessage", {"chat_id": chat_id, "text": "✅ ارسال شد."})

def process_vote(chat_id, user_id, cq):
    if not check_membership(user_id):
        bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "عضو کانال نیستید", "show_alert": True})
        return
    data = cq["data"].split("_")
    p_id, opt_idx = data[1], int(data[2])
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, votes, voters, img_id FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    if row:
        voters = json.loads(row[3])
        if user_id in voters:
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "قبلاً رای داده‌اید."})
        else:
            votes = json.loads(row[2])
            votes[opt_idx] += 1
            voters.append(user_id)
            cursor.execute("UPDATE polls SET votes=?, voters=? WHERE id=?", (json.dumps(votes), json.dumps(voters), p_id))
            conn.commit()
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "رای ثبت شد."})
    conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
