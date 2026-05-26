import os, json, time, threading
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes
import requests

# ── التهيئة من متغيرات البيئة (تضبطها لاحقاً في Render) ──
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GIST_ID = os.environ.get("GIST_ID")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))   # ضع Chat ID الخاص بك

# معلومات مثبَّتة
pinned_msg_data = {}  # chat_id -> message_id

# ── قراءة البيانات من Gist ──
def fetch_data():
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    gist = r.json()
    file = gist.get("files", {}).get("wuwa_banner.json")
    if not file:
        raise Exception("الملف غير موجود")
    return json.loads(file["content"])

# ── توليد نص العداد ──
def get_countdown_text(phase):
    now = datetime.utcnow()
    try:
        end = datetime.fromisoformat(phase["endDate"])
    except:
        return "⏳ تاريخ غير صحيح"
    diff = end - now
    if diff.total_seconds() <= 0:
        return "✅ انتهت هذه المرحلة"
    d = diff.days
    h, rem = divmod(diff.seconds, 3600)
    m, s = divmod(rem, 60)
    bar_len = 20
    total_seconds = 21*86400  # فترة تقديرية
    progress = max(0, min(1, diff.total_seconds() / total_seconds))
    filled = int(bar_len * progress)
    bar = "█" * filled + "░" * (bar_len - filled)
    return (
        f"<b>{phase['label']}</b>\n"
        f"<code>{d} يوم {h:02d}:{m:02d}:{s:02d}</code>\n"
        f"<code>{bar} {progress*100:.0f}%</code>\n"
        f"الشخصيات: {phase.get('characters','—')}"
    )

# ── أوامر البوت ──
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك في بوت متتبع بنرات Wuthering Waves.\n"
        "استخدم /countdown لرؤية العداد الحالي.\n"
        "للمشرفين: /setpin لتفعيل العداد المثبت في القناة."
    )

async def cmd_countdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = fetch_data()
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في جلب البيانات: {e}")
        return
    # عرض الطورين (يمكن تحسينه لاختيار الطور الحالي)
    p1 = data.get("phase1", {})
    p2 = data.get("phase2", {})
    msg = "🔮 <b>العد التنازلي للبنرات</b>\n\n"
    msg += get_countdown_text(p1) + "\n\n" if p1.get("endDate") else ""
    msg += get_countdown_text(p2) if p2.get("endDate") else ""
    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_setpin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمشرف فقط.")
        return
    chat_id = update.effective_chat.id
    # إرسال رسالة أولية
    try:
        data = fetch_data()
    except Exception as e:
        await update.message.reply_text(f"فشل جلب البيانات: {e}")
        return
    p1 = data.get("phase1")
    if not p1:
        await update.message.reply_text("لا توجد بيانات للطور الأول.")
        return
    msg_text = get_countdown_text(p1)
    sent = await context.bot.send_message(chat_id, msg_text, parse_mode="HTML")
    # تثبيت الرسالة (يحتاج صلاحية Admin)
    try:
        await context.bot.pin_chat_message(chat_id, sent.message_id)
    except Exception as e:
        await update.message.reply_text(f"تم إرسال الرسالة ولكن تعذّر التثبيت: {e}")
    pinned_msg_data[chat_id] = sent.message_id
    await update.message.reply_text("✅ تم تفعيل العداد المثبت وسيتم تحديثه كل 30 ثانية.")

async def cmd_stoppin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    chat_id = update.effective_chat.id
    if chat_id in pinned_msg_data:
        try:
            await context.bot.unpin_chat_message(chat_id, pinned_msg_data[chat_id])
        except:
            pass
        del pinned_msg_data[chat_id]
        await update.message.reply_text("تم إيقاف التحديث التلقائي.")
    else:
        await update.message.reply_text("لا يوجد عداد مثبت حالياً.")

# ── حلقة التحديث التلقائي للعدادات المثبتة ──
def update_loop(app):
    while True:
        time.sleep(30)  # كل 30 ثانية
        if not pinned_msg_data:
            continue
        try:
            data = fetch_data()
        except:
            continue
        p1 = data.get("phase1")
        if not p1:
            continue
        text = get_countdown_text(p1)
        for chat_id, msg_id in list(pinned_msg_data.items()):
            try:
                app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    parse_mode="HTML"
                )
            except Exception as e:
                # إذا فشل التعديل (مثلاً حُذفت الرسالة)، نزيلها
                if "message to edit not found" in str(e).lower():
                    del pinned_msg_data[chat_id]

# ── بدء التطبيق ──
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("countdown", cmd_countdown))
    app.add_handler(CommandHandler("setpin", cmd_setpin))
    app.add_handler(CommandHandler("stoppin", cmd_stoppin))

    # تشغيل خيط التحديث
    t = threading.Thread(target=update_loop, args=(app,), daemon=True)
    t.start()

    # تشغيل البوت (polling)
    app.run_polling()

if __name__ == "__main__":
    main()