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
    c.execute("""CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id TEXT,
        question TEXT,
        options TEXT,
        votes TEXT,
        voters TEXT,
        img_id TEXT
    )""")
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
            [{"text": "📂 نظرسنجی‌های من"}, {"text": "📊 گزارش آماری"}],
            [{"text": "🔗 اتصال کانال"}]
        ],
        "resize_keyboard": True
    }

def back_btn():
    return {"keyboard": [[{"text": "🔙 بازگشت به منوی اصلی"}]], "resize_keyboard": True}

# --- ساخت متن آماری برای داخل بازو ---
def get_stats_text(q, opts, votes_list):
    total = sum(votes_list)
    text = f"📊 **{q}**\n\n"
    for i, opt in enumerate(opts):
        count = votes_list[i]
        percent = int((count / total) * 100) if total > 0 else 0
        bar = "🟦" * (percent // 10) + "⬜" * (10 - (percent // 10))
        text += f"{opt}\n{bar} {percent}% ({count} رأی)\n\n"
    text += f"👥 مجموع آرا: {total}"
    return text

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET": return "Bot is Active", 200
    
    update = request.get_json(silent=True)
    if not update: return "ok", 200

    if "message" in update:
        msg = update["message"]
        cid, uid, txt = msg["chat"]["id"], str(msg["from"]["id"]), msg.get("text", "")

        if txt in ["/start", "🔙 بازگشت به منوی اصلی"]:
            user_state[uid] = None
            bot_api("sendMessage", {"chat_id": cid, "text": "🏠 منوی اصلی:", "reply_markup": main_menu()})
            return "ok", 200

        if txt == "➕ ساخت نظرسنجی جدید":
            user_state[uid] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {"chat_id": cid, "text": "❓ سوال نظرسنجی را بنویسید:", "reply_markup": back_btn()})
            return "ok", 200

        if txt in ["📂 نظرسنجی‌های من", "📊 گزارش آماری"]:
            conn = sqlite3.connect("bot_data.db")
            c = conn.cursor()
            c.execute("SELECT id, question FROM polls WHERE creator_id=?", (uid,))
            rows = c.fetchall()
            conn.close()
            if not rows:
                bot_api("sendMessage", {"chat_id": cid, "text": "📭 لیستی یافت نشد."})
            else:
                btns = [[{"text": f"📊 {r[1][:25]}", "callback_data": f"rep_{r[0]}"}] for r in rows]
                bot_api("sendMessage", {"chat_id": cid, "text": "📂 یکی را انتخاب کنید:", "reply_markup": {"inline_keyboard": btns}})
            return "ok", 200

        if txt == "🔗 اتصال کانال":
            user_state[uid] = {"step": "get_ch"}
            bot_api("sendMessage", {"chat_id": cid, "text": "📢 آیدی کانال را بفرستید (مثال: @wamsara):\n⚠️ حتماً بازو را ابتدا ادمین کانال کنید.", "reply_markup": back_btn()})
            return "ok", 200

        # --- مدیریت مراحل ---
        state = user_state.get(uid)
        if state:
            if state["step"] == "get_q" and txt:
                state["q"], state["step"] = txt, "get_opt"
                bot_api("sendMessage", {"chat_id": cid, "text": "✅ سوال ثبت شد. حالا گزینه‌ها را یکی‌یکی بفرستید:", 
                    "reply_markup": {"inline_keyboard": [[{"text": "🏁 پایان و ثبت", "callback_data": "finish"}]]}})
            elif state["step"] == "get_opt" and txt:
                state["opts"].append(txt)
                bot_api("sendMessage", {"chat_id": cid, "text": f"📥 گزینه {len(state['opts'])} ثبت شد. بعدی؟", 
                    "reply_markup": {"inline_keyboard": [[{"text": "🏁 پایان و ثبت", "callback_data": "finish"}]]}})
            elif state["step"] == "get_ch" and txt:
                ch_id = txt.strip()
                # بررسی ادمین بودن
                res = bot_api("getChatMember", {"chat_id": ch_id, "user_id": int(TOKEN.split(":")[0])})
                if res and res.status_code == 200:
                    conn = sqlite3.connect("bot_data.db")
                    conn.cursor().execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (uid, ch_id))
                    conn.commit() ; conn.close()
                    user_state[uid] = None
                    bot_api("sendMessage", {"chat_id": cid, "text": f"✅ کانال {ch_id} با موفقیت متصل شد.", "reply_markup": main_menu()})
                else:
                    bot_api("sendMessage", {"chat_id": cid, "text": "❌ خطا! بازو در این کانال ادمین نیست یا آیدی اشتباه است."})
            elif state["step"] == "wait_img" and "photo" in msg:
                state["img"] = msg["photo"][-1]["file_id"]
                save_final(uid, cid)

    if "callback_query" in update:
        cq = update["callback_query"]
        uid, cid, data = str(cq["from"]["id"]), cq["message"]["chat"]["id"], cq["data"]

        if data == "finish":
            if len(user_state[uid].get("opts", [])) < 2:
                bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "⚠️ حداقل ۲ گزینه!", "show_alert": True})
            else:
                bot_api("sendMessage", {"chat_id": cid, "text": "🖼 آیا مایل به افزودن تصویر هستید؟", 
                    "reply_markup": {"inline_keyboard": [[{"text": "📸 بله", "callback_data": "add_i"}, {"text": "⏭ خیر", "callback_data": "no_i"}]]}})

        elif data == "add_i":
            user_state[uid]["step"] = "wait_img"
            bot_api("sendMessage", {"chat_id": cid, "text": "📸 تصویر را ارسال کنید:"})
        
        elif data == "no_i":
            user_state[uid]["img"] = None
            save_final(uid, cid)

        elif data.startswith("rep_"):
            pid = data.split("_")[1]
            show_admin_report(cid, uid, pid)

        elif data.startswith("preview_"):
            pid = data.split("_")[1]
            show_preview(cid, uid, pid)

        elif data.startswith("pub_"):
            pid = data.split("_")[1]
            publish_to_channel(cid, uid, pid)

        elif data.startswith("del_"):
            pid = data.split("_")[1]
            conn = sqlite3.connect("bot_data.db")
            conn.cursor().execute("DELETE FROM polls WHERE id=?", (pid,))
            conn.commit() ; conn.close()
            bot_api("sendMessage", {"chat_id": cid, "text": "🗑 نظرسنجی حذف شد.", "reply_markup": main_menu()})

        elif data.startswith("vote_"):
            handle_vote(cq)

    return "ok", 200

def save_final(uid, cid):
    s = user_state[uid]
    conn = sqlite3.connect("bot_data.db")
    conn.cursor().execute("INSERT INTO polls (creator_id, question, options, votes, voters, img_id) VALUES (?,?,?,?,?,?)",
        (uid, s["q"], json.dumps(s["opts"], ensure_ascii=False), json.dumps([0]*len(s["opts"])), "[]", s.get("img")))
    conn.commit() ; conn.close()
    user_state[uid] = None
    bot_api("sendMessage", {"chat_id": cid, "text": "✅ نظرسنجی ذخیره شد.", "reply_markup": main_menu()})

def show_admin_report(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT question, options, votes FROM polls WHERE id=?", (pid,))
    r = c.fetchone()
    conn.close()
    if r:
        text = get_stats_text(r[0], json.loads(r[1]), json.loads(r[2]))
        btns = [[{"text": "👁 پیش‌نمایش و انتشار", "callback_data": f"preview_{pid}"}], [{"text": "🗑 حذف", "callback_data": f"del_{pid}"}]]
        bot_api("sendMessage", {"chat_id": cid, "text": text, "reply_markup": {"inline_keyboard": btns}})

def show_preview(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT question, options, img_id FROM polls WHERE id=?", (pid,))
    p = c.fetchone()
    conn.close()
    if p:
        q, opts, img = p[0], json.loads(p[1]), p[2]
        text = f"📊 **{q}**\n\n" + "\n".join([f"▫️ {o}" for o in opts]) + f"\n\n━━━━━━━━━━━━\n🤖 @PollFarsiBot"
        btns = [[{"text": "🚀 تایید و انتشار در کانال", "callback_data": f"pub_{pid}"}]]
        if img: bot_api("sendPhoto", {"chat_id": cid, "photo": img, "caption": text, "reply_markup": {"inline_keyboard": btns}})
        else: bot_api("sendMessage", {"chat_id": cid, "text": text, "reply_markup": {"inline_keyboard": btns}})

def publish_to_channel(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT channel_id FROM channels WHERE user_id=?", (uid,))
    ch = c.fetchone()
    if not ch:
        bot_api("sendMessage", {"chat_id": cid, "text": "❌ ابتدا از منو، کانال را متصل کنید."})
        return
    c.execute("SELECT question, options, img_id FROM polls WHERE id=?", (pid,))
    p = c.fetchone()
    conn.close()
    q, opts, img = p[0], json.loads(p[1]), p[2]
    text = f"📊 **{q}**\n\n" + "\n".join([f"▫️ {o}" for o in opts]) + f"\n\n━━━━━━━━━━━━\n🤖 @PollFarsiBot"
    btns = [[{"text": str(o), "callback_data": f"vote_{pid}_{i}"}] for i, o in enumerate(opts)]
    if img: bot_api("sendPhoto", {"chat_id": ch[0], "photo": img, "caption": text, "reply_markup": {"inline_keyboard": btns}})
    else: bot_api("sendMessage", {"chat_id": ch[0], "text": text, "reply_markup": {"inline_keyboard": btns}})
    bot_api("sendMessage", {"chat_id": cid, "text": "🚀 در کانال منتشر شد!"})

def handle_vote(cq):
    uid, data = str(cq["from"]["id"]), cq["data"]
    _, pid, idx = data.split("_")
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT votes, voters FROM polls WHERE id=?", (pid,))
    r = c.fetchone()
    if r:
        votes, voters = json.loads(r[0]), json.loads(r[1])
        if uid in voters:
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "⚠️ قبلاً رأی داده‌اید!", "show_alert": True})
        else:
            votes[int(idx)] += 1
            voters.append(uid)
            c.execute("UPDATE polls SET votes=?, voters=? WHERE id=?", (json.dumps(votes), json.dumps(voters), pid))
            conn.commit()
            bot_api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "✅ رأی ثبت شد."})
    conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
