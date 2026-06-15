import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = "https://tapi.bale.ai/bot" + str(TOKEN)

def bot_api(method, data=None):
    try:
        r = requests.post(BASE_URL + "/" + method, json=data, timeout=20)
        return r
    except Exception as e:
        print("bot_api error:", e)
        return None

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

def main_menu():
    return {
        "keyboard": [
            [{"text": "➕ ساخت نظرسنجی جدید"}],
            [{"text": "📂 نظرسنجی‌های من"}],
            [{"text": "🔗 اتصال کانال"}]
        ],
        "resize_keyboard": True
    }

def save_poll(uid, cid, img_id=None):
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
        state["question"],
        json.dumps(state["opts"], ensure_ascii=False),
        json.dumps([0] * len(state["opts"])),
        "[]",
        img_id
    ))

    conn.commit()
    conn.close()

    user_state[uid] = None

    bot_api("sendMessage", {
        "chat_id": cid,
        "text": "🎉 نظرسنجی با موفقیت ساخته شد.",
        "reply_markup": main_menu()
    })

def show_my_polls(cid, uid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT id, question FROM polls WHERE creator_id=? ORDER BY id DESC", (uid,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot_api("sendMessage", {
            "chat_id": cid,
            "text": "📭 شما هنوز هیچ نظرسنجی نساخته‌اید."
        })
        return

    btns = []
    for r in rows:
        btns.append([{
            "text": "📊 " + str(r[1])[:25],
            "callback_data": "rep_" + str(r[0])
        }])

    bot_api("sendMessage", {
        "chat_id": cid,
        "text": "📂 لیست نظرسنجی‌های شما:",
        "reply_markup": {"inline_keyboard": btns}
    })

def show_report(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT question, options, votes FROM polls WHERE id=? AND creator_id=?", (pid, uid))
    row = c.fetchone()
    conn.close()

    if not row:
        bot_api("sendMessage", {
            "chat_id": cid,
            "text": "❌ نظرسنجی پیدا نشد."
        })
        return

    q = row[0]
    opts = json.loads(row[1])
    votes = json.loads(row[2])

    total = sum(votes)
    text = "📊 گزارش نظرسنجی\n\n❓ " + q + "\n\n"

    for i in range(len(opts)):
        p = int((votes[i] / total) * 100) if total > 0 else 0
        text += "🔹 " + str(opts[i]) + " — " + str(p) + "% (" + str(votes[i]) + " رای)\n"

    text += "\n👥 مجموع آرا: " + str(total)

    bot_api("sendMessage", {
        "chat_id": cid,
        "text": text,
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "📢 انتشار در کانال", "callback_data": "pub_" + str(pid)}]
            ]
        }
    })

def publish(cid, uid, pid):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()

    c.execute("SELECT channel_id FROM channels WHERE user_id=?", (uid,))
    ch = c.fetchone()

    if not ch:
        conn.close()
        bot_api("sendMessage", {
            "chat_id": cid,
            "text": "❌ ابتدا کانال خود را متصل کنید."
        })
        return

    channel = ch[0]

    c.execute("SELECT question, options, img_id FROM polls WHERE id=? AND creator_id=?", (pid, uid))
    row = c.fetchone()
    conn.close()

    if not row:
        bot_api("sendMessage", {
            "chat_id": cid,
            "text": "❌ نظرسنجی پیدا نشد."
        })
        return

    q = row[0]
    opts = json.loads(row[1])
    img_id = row[2]

    buttons = []
    for i, o in enumerate(opts):
        buttons.append([{
            "text": str(o),
            "callback_data": "vote_" + str(pid) + "_" + str(i)
        }])

    payload = {
        "reply_markup": {"inline_keyboard": buttons}
    }

    if img_id:
        payload["chat_id"] = channel
        payload["photo"] = img_id
        payload["caption"] = "📊 " + q
        bot_api("sendPhoto", payload)
    else:
        payload["chat_id"] = channel
        payload["text"] = "📊 " + q
        bot_api("sendMessage", payload)

    bot_api("sendMessage", {
        "chat_id": cid,
        "text": "✅ نظرسنجی در کانال منتشر شد."
    })

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "GET":
        return "Bot Active", 200

    update = request.get_json(silent=True)
    if not update:
        return "ok", 200

    # =========================
    # پیام‌ها
    # =========================
    if "message" in update:
        msg = update["message"]
        cid = msg["chat"]["id"]
        uid = str(msg["from"]["id"])
        txt = msg.get("text", "")

        if txt == "/start":
            user_state[uid] = None
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "👋 سلام\nبه ربات نظرسنجی خوش آمدید.",
                "reply_markup": main_menu()
            })
            return "ok", 200

        if txt == "➕ ساخت نظرسنجی جدید":
            user_state[uid] = {
                "step": "get_question",
                "question": "",
                "opts": [],
                "img_id": None
            }
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "❓ لطفاً سوال نظرسنجی را ارسال کنید.",
                "reply_markup": {"remove_keyboard": True}
            })
            return "ok", 200

        if txt == "📂 نظرسنجی‌های من":
            show_my_polls(cid, uid)
            return "ok", 200

        if txt == "🔗 اتصال کانال":
            user_state[uid] = {"step": "get_channel"}
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "📢 آیدی کانال را ارسال کنید.\nمثال: @mychannel"
            })
            return "ok", 200

        state = user_state.get(uid)

        if state and state.get("step") == "get_question" and txt:
            state["question"] = txt
            state["step"] = "get_option"
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "✅ سوال ثبت شد.\n\n🔹 حالا گزینه‌ها را یکی‌یکی بفرستید.\n⚠️ حداقل ۲ گزینه لازم است.",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "🏁 اتمام و ثبت نهایی", "callback_data": "finish"}]
                    ]
                }
            })
            return "ok", 200

        if state and state.get("step") == "get_option" and txt:
            state["opts"].append(txt)
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "➕ گزینه ثبت شد: " + txt,
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "🏁 اتمام و ثبت نهایی", "callback_data": "finish"}]
                    ]
                }
            })
            return "ok", 200

        if state and state.get("step") == "get_channel" and txt:
            channel = txt.strip()

            r = bot_api("getChatMember", {
                "chat_id": channel,
                "user_id": int(TOKEN.split(":")[0]) if TOKEN and ":" in TOKEN else 0
            })

            if r and r.status_code == 200:
                st = r.json().get("result", {}).get("status")
                if st in ["administrator", "creator"]:
                    conn = sqlite3.connect("bot_data.db")
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO channels (user_id, channel_id) VALUES (?, ?)", (uid, channel))
                    conn.commit()
                    conn.close()

                    user_state[uid] = None
                    bot_api("sendMessage", {
                        "chat_id": cid,
                        "text": "✅ کانال با موفقیت متصل شد.",
                        "reply_markup": main_menu()
                    })
                else:
                    bot_api("sendMessage", {
                        "chat_id": cid,
                        "text": "❌ ابتدا ربات را ادمین کانال کنید."
                    })
            else:
                bot_api("sendMessage", {
                    "chat_id": cid,
                    "text": "❌ کانال پیدا نشد یا دسترسی بررسی نشد."
                })
            return "ok", 200

        if "photo" in msg and state and state.get("step") == "waiting_image":
            file_id = msg["photo"][-1]["file_id"]
            state["img_id"] = file_id
            save_poll(uid, cid, file_id)
            return "ok", 200

    # =========================
    # کال‌بک‌ها
    # =========================
    if "callback_query" in update:
        cq = update["callback_query"]
        uid = str(cq["from"]["id"])
        cid = cq["message"]["chat"]["id"]
        data = cq["data"]

        if data == "finish":
            state = user_state.get(uid)
            if not state or len(state.get("opts", [])) < 2:
                bot_api("answerCallbackQuery", {
                    "callback_query_id": cq["id"],
                    "text": "❌ حداقل ۲ گزینه لازم است.",
                    "show_alert": True
                })
                return "ok", 200

            state["step"] = "ask_image"
            bot_api("sendMessage", {
                "chat_id": cid,
                "text": "🖼 آیا می‌خواهید برای این نظرسنجی تصویر اضافه کنید؟",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "✅ افزودن تصویر", "callback_data": "add_image"}],
                        [{"text": "⏭ بدون تصویر", "callback_data": "skip_image"}]
                    ]
                }
            })
            return "ok", 200

        if data == "add_image":
            state = user_state.get(uid)
            if state:
                state["step"] = "waiting_image"
                bot_api("sendMessage", {
                    "chat_id": cid,
                    "text": "📸 لطفاً تصویر را ارسال کنید."
                })
            return "ok", 200

        if data == "skip_image":
            save_poll(uid, cid, None)
            return "ok", 200

        if data.startswith("rep_"):
            pid = data.split("_")[1]
            show_report(cid, uid, pid)
            return "ok", 200

        if data.startswith("pub_"):
            pid = data.split("_")[1]
            publish(cid, uid, pid)
            return "ok", 200

    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
