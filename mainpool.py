import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

# --- تنظیمات محیطی ---
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
        print("Error DB: " + str(e))

init_db()
user_state = {}

def bot_api(method, data=None):
    if not TOKEN: return None
    try:
        res = requests.post(BASE_URL + "/" + method, json=data, timeout=15)
        return res
    except: return None

def check_membership(uid):
    try:
        r = bot_api("getChatMember", {"chat_id": REQUIRED_CHANNEL, "user_id": int(uid)})
        if r and r.status_code == 200:
            s = r.json().get("result", {}).get("status")
            return s in ["member", "administrator", "creator"]
    except: pass
    return False

def show_my_polls(cid, uid):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, question FROM polls WHERE creator_id=?", (uid,))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        bot_api("sendMessage", {"chat_id": cid, "text": "📭 شما هنوز هیچ نظرسنجی نساخته‌اید!"})
        return
    btns = [[{"text": "📊 " + str(r[1][:25]), "callback_data": "rep_" + str(r[0])}] for r in rows]
    bot_api("sendMessage", {"chat_id": cid, "text": "📂 **لیست نظرسنجی‌های شما:**\nبرای مدیریت یا مشاهده گزارش روی یکی از موارد زیر بزنید:", "reply_markup": {"inline_keyboard": btns}})

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET": return "Bot is Active 🚀", 200
    
    update = request.get_json(silent=True)
    if not update: return "ok", 200

    if "message" in update:
        msg = update["message"]
        cid, uid = msg["chat"]["id"], str(msg["from"]["id"])
        txt = msg.get("text", "")

        if txt == "/start":
            user_state[uid] = None
            kb = {"keyboard": [[{"text": "➕ ساخت نظرسنجی جدید"}], [{"text": "🗂 نظرسنجی‌های من"}]], "resize_keyboard": True}
            bot_api("sendMessage", {"chat_id": cid, "text": "👋 سلام! به بازوی نظرسنجی پیشرفته خوش آمدید.\n\n💎 با این ربات می‌توانید نظرسنجی‌های حرفه‌ای بسازید و در کانال خود منتشر کنید.", "reply_markup": kb})
        
        elif txt == "➕ ساخت نظرسنجی جدید":
            user_state[uid] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {"chat_id": cid, "text": "❓ **سوال نظرسنجی را بفرستید:**", "reply_markup": {"remove_keyboard": True}})
            
        elif uid in user_state and user_state[uid]:
            state = user_state[uid]
            if state["step"] == "get_q" and txt:
                state["q"] = txt
                state["step"] = "get_opts"
                bot_api("sendMessage", {"chat_id": cid, "text": "✅ سوال ثبت شد.\n\n🔹 حالا **گزینه‌ها** را یکی‌یکی بفرستید.\n⚠️ حداقل ۲ گزینه وارد کنید.", "reply_markup": {"inline_keyboard": [[{"text": "🏁 اتمام و ثبت نهایی", "callback_data": "finish"}]]}})
            elif state["step"] == "get_opts" and txt:
                state["opts"].append(txt)
                bot_api("sendMessage", {"chat_id": cid, "text": "📥 گزینه «" + txt + "» اضافه شد.\n\nدیگر چه گزینه‌ای اضافه شود؟", "reply_markup": {"inline_keyboard": [[{"text": "🏁 اتمام و ثبت نهایی", "callback_data": "finish"}]]}})

    elif "callback_query" in update:
        handle_callbacks(update["callback_query"])

    return "ok", 200

def handle_callbacks(cq):
    uid, cid, data = str(cq["from"]["id"]), cq["message"]["chat"]["id"], cq["data"]
    
    if data == "finish":
        state = user_state.get(uid)
        if state and len(state["opts"]) >= 2:
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO polls (creator_id, question, options, votes, voters) VALUES (?, ?, ?, ?, ?)",
                           (uid, state["q"], json.dumps(state["opts"]), json.dumps([0]*len(state["opts"])), "[]"))
            conn.commit()
            conn.close()
            user_state[uid] = None
            bot_api("sendMessage", {"chat_id": cid, "text": "🎉 تبریک! نظرسنجی شما با موفقیت ساخته شد."})
            show_my_polls(cid, uid)
        else:
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "❌ خطا: حداقل ۲ گزینه لازم است!", "show_alert": True})

    elif data.startswith("rep_"):
        show_full_report(cid, uid, data.split("_")[1])

    elif data.startswith("del_"):
        p_id = data.split("_")[1]
        conn = sqlite3.connect('bot_data.db')
        conn.cursor().execute("DELETE FROM polls WHERE id=?", (p_id,))
        conn.commit()
        conn.close()
        bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "🗑 نظرسنجی حذف شد."})
        show_my_polls(cid, uid)

def show_full_report(cid, uid, p_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT question, options, votes FROM polls WHERE id=?", (p_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        q, opts, v_list = row[0], json.loads(row[1]), json.loads(row[2])
        tot = sum(v_list)
        report = "📊 **گزارش نظرسنجی:**\n\n❓ " + str(q) + "\n" + ("─"*15) + "\n"
        for i, o in enumerate(opts):
            p = (v_list[i]/tot*100) if tot > 0 else 0
            report += "🔹 " + str(o) + " ⮕ " + str(int(p)) + "% (" + str(v_list[i]) + " رای)\n"
        
        report += "\n👥 مجموع آرا: " + str(tot)
        btns = [
            [{"text": "📢 انتشار در کانال", "callback_data": "pub_" + str(p_id)}],
            [{"text": "🔄 بروزرسانی", "callback_data": "rep_" + str(p_id)}, {"text": "🗑 حذف", "callback_data": "del_" + str(p_id)}]
        ]
        bot_api("sendMessage", {"chat_id": cid, "text": report, "reply_markup": {"inline_keyboard": btns}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
