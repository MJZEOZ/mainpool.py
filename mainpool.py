import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ===============================
# ارتباط با API بله
# ===============================
def bot_api(method, data=None):
    try:
        r = requests.post(f"{BASE_URL}/{method}", json=data, timeout=20)
        return r
    except:
        return None

# ===============================
# دیتابیس
# ===============================
def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id TEXT,
        question TEXT,
        options TEXT,
        votes TEXT,
        voters TEXT,
        img_id TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS channels (
        user_id TEXT PRIMARY KEY,
        channel_id TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()
user_state = {}

# ===============================
# کیبوردها
# ===============================
def main_menu():
    return {
        "keyboard": [
            [{"text": "➕ ساخت نظرسنجی جدید"}],
            [{"text": "📂 نظرسنجی‌های من"}],
            [{"text": "📊 گزارش آماری"}],
            [{"text": "🔗 اتصال کانال"}]
        ],
        "resize_keyboard": True
    }

def back_menu():
    return {
        "keyboard": [[{"text": "🔙 بازگشت به منوی اصلی"}]],
        "resize_keyboard": True
    }

# ===============================
# ساخت متن آماری
# ===============================
def get_poll_stats_text(question, opts, votes):
    total = sum(votes)
    text = f"📊 {question}\n\n"

    for i, opt in enumerate(opts):
        count = votes[i]
        percent = int((count / total) * 100) if total > 0 else 0
        bar = "🟦" * (percent // 10) + "⬜" * (10 - (percent // 10))
        text += f"{opt}\n{bar} {percent}% ({count} رأی)\n\n"

    text += f"👥 مجموع آرا: {total}"
    return text

# ===============================
# ذخیره نهایی نظرسنجی
# ===============================
def complete_save(uid, cid):
    state = user_state.get(uid)
    if not state:
        return

    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO polls (creator_id, question, options, votes, voters, img_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        uid,
        state["q"],
        json.dumps(state["opts"], ensure_ascii=False),
        json.dumps([0]*len(state["opts"])),
        "[]",
        state.get("img")
    ))

    conn.commit()
    conn.close()

    user_state[uid] = None

    bot_api("sendMessage", {
        "chat_id": cid,
        "text": "✅ نظرسنجی با موفقیت ذخیره شد.",
        "reply_markup": main_menu()
    })

# ===============================
# انتشار در کانال (بدون آمار)
# ===============================
def publish_to_channel(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()

    c.execute("SELECT channel_id FROM channels WHERE user_id=?", (uid,))
    ch = c.fetchone()
    if not ch:
        bot_api("sendMessage", {"chat_id": cid, "text": "❌ ابتدا کانال را متصل کنید."})
        conn.close()
        return

    channel_id = ch[0]

    c.execute("SELECT question, options, img_id FROM polls WHERE id=?", (pid,))
    row = c.fetchone()
    conn.close()

    if not row:
        return

    q = row[0]
    opts = json.loads(row[1])
    img = row[2]

    text = "📊 " + q + "\n\n"
    for o in opts:
        text += "▫️ " + o + "\n"

    text += "\n━━━━━━━━━━━━\n"
    text += "🤖 ساخته شده توسط:\n"
    text += "@PollFarsiBot"

    buttons = []
    for i, o in enumerate(opts):
        buttons.append([{
            "text": o,
            "callback_data": f"vote_{pid}_{i}"
        }])

    if img:
        bot_api("sendPhoto", {
            "chat_id": channel_id,
            "photo": img,
            "caption": text,
            "reply_markup": {"inline_keyboard": buttons}
        })
    else:
        bot_api("sendMessage", {
            "chat_id": channel_id,
            "text": text,
            "reply_markup": {"inline_keyboard": buttons}
        })

    bot_api("sendMessage", {
        "chat_id": cid,
        "text": "🚀 نظرسنجی در کانال منتشر شد."
    })

# ===============================
# مدیریت رأی
# ===============================
def handle_vote(cq):
    uid = str(cq["from"]["id"])
    data = cq["data"]
    cq_id = cq["id"]

    _, pid, opt_index = data.split("_")
    opt_index = int(opt_index)

    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT votes, voters FROM polls WHERE id=?", (pid,))
    row = c.fetchone()

    if not row:
        conn.close()
        return

    votes = json.loads(row[0])
    voters = json.loads(row[1])

    if uid in voters:
        bot_api("answerCallbackQuery", {
            "callback_query_id": cq_id,
            "text": "⚠️ شما قبلاً رأی داده‌اید.",
            "show_alert": True
        })
        conn.close()
        return

    votes[opt_index] += 1
    voters.append(uid)

    c.execute("UPDATE polls SET votes=?, voters=? WHERE id=?",
              (json.dumps(votes), json.dumps(voters), pid))

    conn.commit()
    conn.close()

    bot_api("answerCallbackQuery", {
        "callback_query_id": cq_id,
        "text": "✅ رأی شما ثبت شد."
    })

# ===============================
# Flask
# ===============================
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return "Bot Running", 200

    update = request.get_json(silent=True)
    if not update:
        return "ok", 200

    # =====================
    # پیام‌ها
    # =====================
    if "message" in update:
        msg = update["message"]
        cid = msg["chat"]["id"]
        uid = str(msg["from"]["id"])
        txt = msg.get("text", "")

        if txt in ["/start", "🔙 بازگشت به منوی اصلی"]:
            user_state[uid] = None
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "🏠 به منوی اصلی خوش آمدید.",
                "reply_markup": main_menu()
            })
            return "ok", 200

        if txt == "➕ ساخت نظرسنجی جدید":
            user_state[uid] = {"step": "get_q", "opts": []}
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "❓ سوال را ارسال کنید:",
                "reply_markup": back_menu()
            })
            return "ok", 200

        if txt == "📂 نظرسنجی‌های من" or txt == "📊 گزارش آماری":
            conn = sqlite3.connect("bot_data.db")
            c = conn.cursor()
            c.execute("SELECT id, question FROM polls WHERE creator_id=?", (uid,))
            rows = c.fetchall()
            conn.close()

            if not rows:
                bot_api("sendMessage", {
                    "chat_id": cid,
                    "text": "📭 موردی وجود ندارد."
                })
                return "ok", 200

            btns = []
            for r in rows:
                btns.append([{
                    "text": "📊 " + r[1][:25],
                    "callback_data": f"rep_{r[0]}"
                }])

            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "یکی را انتخاب کنید:",
                "reply_markup": {"inline_keyboard": btns}
            })
            return "ok", 200

        # مراحل ساخت
        state = user_state.get(uid)
        if state:
            if state["step"] == "get_q":
                state["q"] = txt
                state["step"] = "get_opt"
                bot_api("sendMessage", {
                    "chat_id": cid,
                    "text": "✅ سوال ثبت شد.\nگزینه‌ها را یکی‌یکی ارسال کنید:",
                    "reply_markup": {
                        "inline_keyboard": [[{"text": "🏁 پایان", "callback_data": "finish"}]]
                    }
                })

            elif state["step"] == "get_opt":
                state["opts"].append(txt)
                bot_api("sendMessage", {
                    "chat_id": cid,
                    "text": f"✅ گزینه {len(state['opts'])} ثبت شد.",
                    "reply_markup": {
                        "inline_keyboard": [[{"text": "🏁 پایان", "callback_data": "finish"}]]
                    }
                })

    # =====================
    # کال‌بک‌ها
    # =====================
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq["data"]
        cid = cq["message"]["chat"]["id"]
        uid = str(cq["from"]["id"])

        if data == "finish":
            if len(user_state[uid]["opts"]) < 2:
                bot_api("answerCallbackQuery", {
                    "callback_query_id": cq["id"],
                    "text": "حداقل ۲ گزینه لازم است",
                    "show_alert": True
                })
            else:
                complete_save(uid, cid)

        elif data.startswith("rep_"):
            pid = data.split("_")[1]
            conn = sqlite3.connect("bot_data.db")
            c = conn.cursor()
            c.execute("SELECT question, options, votes FROM polls WHERE id=?", (pid,))
            row = c.fetchone()
            conn.close()

            if row:
                text = get_poll_stats_text(
                    row[0],
                    json.loads(row[1]),
                    json.loads(row[2])
                )

                bot_api("sendMessage", {
                    "chat_id": cid,
                    "text": text,
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": "👁 پیش‌نمایش", "callback_data": f"preview_{pid}"}],
                            [{"text": "🗑 حذف", "callback_data": f"del_{pid}"}]
                        ]
                    }
                })

        elif data.startswith("preview_"):
            pid = data.split("_")[1]
            conn = sqlite3.connect("bot_data.db")
            c = conn.cursor()
            c.execute("SELECT question, options, img_id FROM polls WHERE id=?", (pid,))
            row = c.fetchone()
            conn.close()

            if row:
                q = row[0]
                opts = json.loads(row[1])
                img = row[2]

                text = "📊 پیش‌نمایش\n\n❓ " + q + "\n\n"
                for o in opts:
                    text += "▫️ " + o + "\n"

                text += "\n━━━━━━━━━━━━\n@PollFarsiBot"

                btns = [
                    [{"text": "🚀 انتشار", "callback_data": f"pub_{pid}"}]
                ]

                if img:
                    bot_api("sendPhoto", {
                        "chat_id": cid,
                        "photo": img,
                        "caption": text,
                        "reply_markup": {"inline_keyboard": btns}
                    })
                else:
                    bot_api("sendMessage", {
                        "chat_id": cid,
                        "text": text,
                        "reply_markup": {"inline_keyboard": btns}
                    })

        elif data.startswith("pub_"):
            pid = data.split("_")[1]
            publish_to_channel(cid, uid, pid)

        elif data.startswith("del_"):
            pid = data.split("_")[1]
            conn = sqlite3.connect("bot_data.db")
            conn.cursor().execute("DELETE FROM polls WHERE id=?", (pid,))
            conn.commit()
            conn.close()

            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "🗑 حذف شد.",
                "reply_markup": main_menu()
            })

        elif data.startswith("vote_"):
            handle_vote(cq)

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
