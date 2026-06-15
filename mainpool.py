import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

# --- تنظیمات توکن ---
TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

def bot_api(method, data=None):
    try:
        r = requests.post(f"{BASE_URL}/{method}", json=data, timeout=20)
        return r
    except:
        return None

# --- راه‌اندازی دیتابیس ---
def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    # جدول نظرسنجی‌ها
    c.execute("""CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id TEXT,
        question TEXT,
        options TEXT,
        votes TEXT,
        voters TEXT,
        img_id TEXT
    )""")
    # جدول کانال‌های متصل
    c.execute("CREATE TABLE IF NOT EXISTS channels (user_id TEXT PRIMARY KEY, channel_id TEXT)")
    conn.commit()
    conn.close()

init_db()
user_state = {}

# --- کیبوردها ---
def main_menu():
    return {
        "keyboard": [
            [{"text": "➕ ساخت نظرسنجی جدید"}],
            [{"text": "📂 نظرسنجی‌های من"}, {"text": "🔗 اتصال کانال"}]
        ],
        "resize_keyboard": True
    }

def back_btn():
    return {"keyboard": [[{"text": "🔙 بازگشت به منوی اصلی"}]], "resize_keyboard": True}

# --- توابع کمکی ---
def get_poll_text(q, opts, votes_list):
    total = sum(votes_list)
    text = f"📊 **{q}**\n\n"
    for i, opt in enumerate(opts):
        count = votes_list[i]
        percent = int((count / total) * 100) if total > 0 else 0
        bar = "🟦" * (percent // 10) + "⬜" * (10 - (percent // 10))
        text += f"{opt}\n{bar} {percent}% ({count} رأی)\n\n"
    text += f"👥 مجموع آرا: {total}"
    return text

def update_poll_msg(pid, channel_id, msg_id=None):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT question, options, votes, img_id FROM polls WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()
    if not row: return

    q, opts, votes_list, img_id = row[0], json.loads(row[1]), json.loads(row[2]), row[3]
    text = get_poll_text(q, opts, votes_list)
    
    btns = []
    for i, o in enumerate(opts):
        btns.append([{"text": str(o), "callback_data": f"vote_{pid}_{i}"}])

    # بله فعلاً editMessageText برای بات‌های معمولی محدودیت دارد، 
    # اما با ارسال مجدد یا روش‌های مشابه در کانال مدیریت می‌شود.
    # در اینجا ما فرض را بر نمایش گزارش آپدیت شده می‌گذاریم.

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET": return "Bot is Running...", 200
    
    update = request.get_json(silent=True)
    if not update: return "ok", 200

    # مدیریت پیام‌ها
    if "message" in update:
        msg = update["message"]
        cid, uid, txt = msg["chat"]["id"], str(msg["from"]["id"]), msg.get("text", "")

        if txt in ["/start", "🔙 بازگشت به منوی اصلی"]:
            user_state[uid] = None
            bot_api("sendMessage", {"chat_id": cid, "text": "🏠 به منوی اصلی برگشتیم. چه کاری انجام دهم؟", "reply_markup": main_menu()})
            return "ok", 200

        if txt == "➕ ساخت نظرسنجی جدید":
            user_state[uid] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {"chat_id": cid, "text": "❓ سوال نظرسنجی را بنویسید:", "reply_markup": back_btn()})
            return "ok", 200

        if txt == "📂 نظرسنجی‌های من":
            conn = sqlite3.connect("bot_data.db")
            c = conn.cursor()
            c.execute("SELECT id, question FROM polls WHERE creator_id=?", (uid,))
            rows = c.fetchall()
            conn.close()
            if not rows:
                bot_api("sendMessage", {"chat_id": cid, "text": "📭 لیست شما خالی است."})
            else:
                btns = [[{"text": f"📊 {r[1][:20]}...", "callback_data": f"rep_{r[0]}"}] for r in rows]
                bot_api("sendMessage", {"chat_id": cid, "text": "📂 لیست نظرسنجی‌های شما:", "reply_markup": {"inline_keyboard": btns}})
            return "ok", 200

        if txt == "🔗 اتصال کانال":
            user_state[uid] = {"step": "get_ch"}
            bot_api("sendMessage", {"chat_id": cid, "text": "📢 آیدی کانال را با @ بفرستید:\n(ربات باید ادمین کانال باشد)", "reply_markup": back_btn()})
            return "ok", 200

        # منطق مراحل (FSM)
        state = user_state.get(uid)
        if state:
            if state["step"] == "get_q":
                state["q"], state["step"] = txt, "get_opt"
                bot_api("sendMessage", {"chat_id": cid, "text": "✅ ثبت شد. حالا گزینه‌ها را یکی‌یکی بفرستید:", 
                    "reply_markup": {"inline_keyboard": [[{"text": "🏁 پایان و ثبت", "callback_data": "finish"}]]}})
            elif state["step"] == "get_opt":
                state["opts"].append(txt)
                bot_api("sendMessage", {"chat_id": cid, "text": f"📥 گزینه {len(state['opts'])} ثبت شد. گزینه بعدی؟", 
                    "reply_markup": {"inline_keyboard": [[{"text": "🏁 پایان و ثبت", "callback_data": "finish"}]]}})
            elif state["step"] == "get_ch":
                # بررسی ادمین بودن
                ch_id = txt.strip()
                res = bot_api("getChatMember", {"chat_id": ch_id, "user_id": int(TOKEN.split(":")[0])})
                if res and res.status_code == 200 and res.json().get("result", {}).get("status") in ["administrator", "creator"]:
                    conn = sqlite3.connect("bot_data.db")
                    conn.cursor().execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (uid, ch_id))
                    conn.commit() ; conn.close()
                    user_state[uid] = None
                    bot_api("sendMessage", {"chat_id": cid, "text": "✅ کانال با موفقیت متصل شد!", "reply_markup": main_menu()})
                else:
                    bot_api("sendMessage", {"chat_id": cid, "text": "❌ خطا! ربات در این کانال ادمین نیست."})
            elif state["step"] == "wait_img" and "photo" in msg:
                state["img"] = msg["photo"][-1]["file_id"]
                complete_save(uid, cid)

    # مدیریت دکمه‌های شیشه‌ای (Callback)
    if "callback_query" in update:
        cq = update["callback_query"]
        uid, cid, data, cq_id = str(cq["from"]["id"]), cq["message"]["chat"]["id"], cq["data"], cq["id"]

        if data == "finish":
            if len(user_state[uid]["opts"]) < 2:
                bot_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "⚠️ حداقل ۲ گزینه!", "show_alert": True})
            else:
                bot_api("sendMessage", {"chat_id": cid, "text": "🖼 تصویر اضافه شود؟", 
                    "reply_markup": {"inline_keyboard": [[{"text": "📸 بله", "callback_data": "add_i"}, {"text": "⏭ خیر", "callback_data": "no_i"}]]}})

        elif data == "add_i":
            user_state[uid]["step"] = "wait_img"
            bot_api("sendMessage", {"chat_id": cid, "text": "📸 تصویر را بفرستید:"})
        
        elif data == "no_i":
            user_state[uid]["img"] = None
            complete_save(uid, cid)

        elif data.startswith("rep_"):
            pid = data.split("_")[1]
            send_report_to_admin(cid, uid, pid)

        elif data.startswith("del_"):
            pid = data.split("_")[1]
            conn = sqlite3.connect("bot_data.db")
            conn.cursor().execute("DELETE FROM polls WHERE id=? AND creator_id=?", (pid, uid))
            conn.commit() ; conn.close()
            bot_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "🗑 حذف شد."})
            bot_api("sendMessage", {"chat_id": cid, "text": "نظرسنجی حذف شد.", "reply_markup": main_menu()})

        elif data.startswith("pub_"):
            pid = data.split("_")[1]
            publish_to_channel(cid, uid, pid)

        elif data.startswith("vote_"):
            handle_vote(cq)

    return "ok", 200

def complete_save(uid, cid):
    s = user_state[uid]
    conn = sqlite3.connect("bot_data.db")
    conn.cursor().execute("INSERT INTO polls (creator_id, question, options, votes, voters, img_id) VALUES (?,?,?,?,?,?)",
        (uid, s["q"], json.dumps(s["opts"]), json.dumps([0]*len(s["opts"])), "[]", s.get("img")))
    conn.commit() ; conn.close()
    user_state[uid] = None
    bot_api("sendMessage", {"chat_id": cid, "text": "✅ نظرسنجی ساخته و ذخیره شد.", "reply_markup": main_menu()})

def send_report_to_admin(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT question, options, votes FROM polls WHERE id=?", (pid,))
    r = c.fetchone()
    conn.close()
    if r:
        text = get_poll_text(r[0], json.loads(r[1]), json.loads(r[2]))
        btns = [[{"text": "📢 انتشار در کانال", "callback_data": f"pub_{pid}"}],
                [{"text": "🗑 حذف نظرسنجی", "callback_data": f"del_{pid}"}]]
        bot_api("sendMessage", {"chat_id": cid, "text": text, "reply_markup": {"inline_keyboard": btns}})

def publish_to_channel(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT channel_id FROM channels WHERE user_id=?", (uid,))
    ch = c.fetchone()
    if not ch:
        bot_api("sendMessage", {"chat_id": cid, "text": "❌ اول کانال را وصل کنید."})
        return
    
    c.execute("SELECT question, options, votes, img_id FROM polls WHERE id=?", (pid,))
    p = c.fetchone()
    conn.close()
    
    q, opts, votes, img = p[0], json.loads(p[1]), json.loads(p[2]), p[3]
    text = get_poll_text(q, opts, votes)
    btns = [[{"text": str(o), "callback_data": f"vote_{pid}_{i}"}] for i, o in enumerate(opts)]
    
    if img:
        bot_api("sendPhoto", {"chat_id": ch[0], "photo": img, "caption": text, "reply_markup": {"inline_keyboard": btns}})
    else:
        bot_api("sendMessage", {"chat_id": ch[0], "text": text, "reply_markup": {"inline_keyboard": btns}})
    bot_api("sendMessage", {"chat_id": cid, "text": "🚀 در کانال منتشر شد!"})

def handle_vote(cq):
    uid, cq_id, data = str(cq["from"]["id"]), cq["id"], cq["data"]
    _, pid, opt_idx = data.split("_")
    opt_idx = int(opt_idx)

    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT options, votes, voters, question FROM polls WHERE id=?", (pid,))
    row = c.fetchone()
    
    if row:
        opts, votes, voters, q = json.loads(row[0]), json.loads(row[1]), json.loads(row[2]), row[3]
        if uid in voters:
            bot_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "⚠️ شما قبلاً رأی داده‌اید!", "show_alert": True})
        else:
            votes[opt_idx] += 1
            voters.append(uid)
            c.execute("UPDATE polls SET votes=?, voters=? WHERE id=?", (json.dumps(votes), json.dumps(voters), pid))
            conn.commit()
            bot_api("answerCallbackQuery", {"callback_query_id": cq_id, "text": "✅ رأی شما ثبت شد."})
            # اینجا می‌توان پیام را در کانال آپدیت کرد (اختیاری)
    conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
