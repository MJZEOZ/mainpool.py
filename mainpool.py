import os
import requests
import sqlite3
import json
from flask import Flask, request

app = Flask(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
BASE_URL = "https://tapi.bale.ai/bot" + str(TOKEN)

def bot_api(method,data=None):
    try:
        return requests.post(BASE_URL + "/" + method,json=data,timeout=15)
    except:
        return None

def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS polls(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id TEXT,
    question TEXT,
    options TEXT,
    votes TEXT,
    voters TEXT,
    img_id TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS channels(
    user_id TEXT,
    channel_id TEXT
    )""")

    conn.commit()
    conn.close()

init_db()

user_state={}

def main_menu():
    return {
        "keyboard":[
            [{"text":"➕ ساخت نظرسنجی"}],
            [{"text":"📂 نظرسنجی های من"}],
            [{"text":"🔗 اتصال کانال"}]
        ],
        "resize_keyboard":True
    }

@app.route("/",methods=["GET","POST"])
def home():

    if request.method=="GET":
        return "Bot Active",200

    update=request.get_json(silent=True)

    if not update:
        return "ok",200

    if "message" in update:

        msg=update["message"]
        cid=msg["chat"]["id"]
        uid=str(msg["from"]["id"])
        txt=msg.get("text")

        if txt=="/start":

            user_state[uid]=None

            bot_api("sendMessage",{
            "chat_id":cid,
            "text":"👋 سلام\nبه ربات نظرسنجی خوش آمدید",
            "reply_markup":main_menu()
            })

        elif txt=="➕ ساخت نظرسنجی":

            user_state[uid]={"step":"q","opts":[]}

            bot_api("sendMessage",{
            "chat_id":cid,
            "text":"❓ سوال نظرسنجی را ارسال کنید",
            "reply_markup":{"remove_keyboard":True}
            })

        elif txt=="📂 نظرسنجی های من":

            conn=sqlite3.connect("bot_data.db")
            c=conn.cursor()

            c.execute("SELECT id,question FROM polls WHERE creator_id=?",(uid,))
            rows=c.fetchall()

            conn.close()

            if not rows:

                bot_api("sendMessage",{
                "chat_id":cid,
                "text":"❌ هنوز نظرسنجی نساخته اید"
                })

            else:

                btn=[]

                for r in rows:
                    btn.append([{
                    "text":"📊 "+str(r[1])[:25],
                    "callback_data":"rep_"+str(r[0])
                    }])

                bot_api("sendMessage",{
                "chat_id":cid,
                "text":"📂 نظرسنجی های شما",
                "reply_markup":{"inline_keyboard":btn}
                })

        elif txt=="🔗 اتصال کانال":

            user_state[uid]={"step":"channel"}

            bot_api("sendMessage",{
            "chat_id":cid,
            "text":"📢 آیدی کانال را ارسال کنید\nمثال:\n@mychannel"
            })

        elif uid in user_state and user_state[uid]:

            state=user_state[uid]

            if state["step"]=="q":

                state["question"]=txt
                state["step"]="opt"

                bot_api("sendMessage",{
                "chat_id":cid,
                "text":"✅ سوال ثبت شد\nگزینه ها را بفرستید",
                "reply_markup":{
                "inline_keyboard":[[
                {"text":"🏁 اتمام گزینه ها","callback_data":"finish"}
                ]]
                }
                })

            elif state["step"]=="opt":

                state["opts"].append(txt)

                bot_api("sendMessage",{
                "chat_id":cid,
                "text":"➕ گزینه اضافه شد",
                "reply_markup":{
                "inline_keyboard":[[
                {"text":"🏁 اتمام گزینه ها","callback_data":"finish"}
                ]]
                }
                })

            elif state["step"]=="channel":

                channel=txt.strip()

                r=bot_api("getChatMember",{
                "chat_id":channel,
                "user_id":TOKEN.split(":")[0]
                })

                if r and r.status_code==200:

                    st=r.json()["result"]["status"]

                    if st in ["administrator","creator"]:

                        conn=sqlite3.connect("bot_data.db")
                        c=conn.cursor()

                        c.execute("DELETE FROM channels WHERE user_id=?",(uid,))
                        c.execute("INSERT INTO channels VALUES(?,?)",(uid,channel))

                        conn.commit()
                        conn.close()

                        user_state[uid]=None

                        bot_api("sendMessage",{
                        "chat_id":cid,
                        "text":"✅ کانال با موفقیت متصل شد",
                        "reply_markup":main_menu()
                        })

                    else:

                        bot_api("sendMessage",{
                        "chat_id":cid,
                        "text":"❌ ابتدا ربات را ادمین کانال کنید"
                        })

                else:

                    bot_api("sendMessage",{
                    "chat_id":cid,
                    "text":"❌ کانال پیدا نشد"
                    })

        if "photo" in msg and uid in user_state:

            state=user_state[uid]

            if state.get("step")=="img":

                file_id=msg["photo"][-1]["file_id"]

                save_poll(uid,cid,file_id)

    if "callback_query" in update:

        cq=update["callback_query"]
        data=cq["data"]
        uid=str(cq["from"]["id"])
        cid=cq["message"]["chat"]["id"]

        if data=="finish":

            state=user_state.get(uid)

            if len(state["opts"])<2:

                bot_api("answerCallbackQuery",{
                "callback_query_id":cq["id"],
                "text":"حداقل ۲ گزینه لازم است",
                "show_alert":True
                })

            else:

                bot_api("sendMessage",{
                "chat_id":cid,
                "text":"🖼 تصویر هم دارید؟",
                "reply_markup":{
                "inline_keyboard":[
                [{"text":"✅ ارسال تصویر","callback_data":"img"}],
                [{"text":"⏭ بدون تصویر","callback_data":"skip"}]
                ]
                }
                })

        elif data=="img":

            user_state[uid]["step"]="img"

            bot_api("sendMessage",{
            "chat_id":cid,
            "text":"📸 تصویر را ارسال کنید"
            })

        elif data=="skip":

            save_poll(uid,cid,None)

        elif data.startswith("rep_"):

            pid=data.split("_")[1]

            show_report(cid,uid,pid)

        elif data.startswith("pub_"):

            pid=data.split("_")[1]

            publish(cid,uid,pid)

    return "ok",200

def save_poll(uid,cid,img):

    state=user_state[uid]

    conn=sqlite3.connect("bot_data.db")
    c=conn.cursor()

    c.execute("INSERT INTO polls VALUES(NULL,?,?,?,?,?,?)",(
    uid,
    state["question"],
    json.dumps(state["opts"]),
    json.dumps([0]*len(state["opts"])),
    "[]",
    img
    ))

    conn.commit()
    conn.close()

    user_state[uid]=None

    bot_api("sendMessage",{
    "chat_id":cid,
    "text":"✅ نظرسنجی ساخته شد",
    "reply_markup":main_menu()
    })

def show_report(cid,uid,pid):

    conn=sqlite3.connect("bot_data.db")
    c=conn.cursor()

    c.execute("SELECT question FROM polls WHERE id=?",(pid,))
    row=c.fetchone()

    conn.close()

    if row:

        bot_api("sendMessage",{
        "chat_id":cid,
        "text":"📊 "+row[0],
        "reply_markup":{
        "inline_keyboard":[[
        {"text":"📢 انتشار در کانال","callback_data":"pub_"+pid}
        ]]
        }
        })

def publish(cid,uid,pid):

    conn=sqlite3.connect("bot_data.db")
    c=conn.cursor()

    c.execute("SELECT channel_id FROM channels WHERE user_id=?",(uid,))
    ch=c.fetchone()

    if not ch:

        bot_api("sendMessage",{
        "chat_id":cid,
        "text":"❌ ابتدا کانال خود را متصل کنید"
        })

        return

    channel=ch[0]

    c.execute("SELECT question,options,img_id FROM polls WHERE id=?",(pid,))
    row=c.fetchone()

    conn.close()

    q=row[0]
    opts=json.loads(row[1])
    img=row[2]

    buttons=[]

    for i,o in enumerate(opts):
        buttons.append([{
        "text":o,
        "callback_data":"vote_"+pid+"_"+str(i)
        }])

    if img:

        bot_api("sendPhoto",{
        "chat_id":channel,
        "photo":img,
        "caption":"📊 "+q,
        "reply_markup":{"inline_keyboard":buttons}
        })

    else:

        bot_api("sendMessage",{
        "chat_id":channel,
        "text":"📊 "+q,
        "reply_markup":{"inline_keyboard":buttons}
        })

    bot_api("sendMessage",{
    "chat_id":cid,
    "text":"✅ نظرسنجی در کانال منتشر شد"
    })

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",8080)))
