from datetime import datetime
import os
import sqlite3
import threading
from flask import Flask
import telebot
from telebot import types

# Bot tokeningiz
TOKEN = "8707409506:AAEj8ZVSuzgkTusgilaVDXTz__U8zVFG4kk"
bot = telebot.TeleBot(TOKEN)

# Sening Telegram Admin ID raqaming
ADMIN_ID = 6766950408  # <-- Agar ID raqaming boshqacha bo'lsa, shu yerdagi raqamni o'zgartirasan

# Railway Volume papkasi (agar local ishlatayotgan bo'lsangiz shunchaki 'database.db' bo'ladi)
DB_DIR = "/app/data"
if not os.path.exists(DB_DIR):
  os.makedirs(DB_DIR, exist_ok=True)

DB_PATH = os.path.join(DB_DIR, "database.db")


# Bazani yaratish va jadvallarni sozlash
def init_db():
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            birth_date TEXT,
            payment_status TEXT DEFAULT 'Tolanmagan ❌',
            payment_date TEXT,
            payment_amount INTEGER DEFAULT 0,
            next_payment_date TEXT,
            lang TEXT DEFAULT 'uz'
        )
    """)
  conn.commit()
  conn.close()


init_db()


# 1 oydan keyingi sanani hisoblaydigan yordamchi funksiya
def add_one_month(dt):
  month = dt.month + 1
  year = dt.year
  if month > 12:
    month = 1
    year += 1
  day = min(
      dt.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
  )
  return dt.replace(year=year, month=month, day=day)


# Ro'yxatdan o'tish jarayoni (Tug'ilgan sana bilan)
@bot.message_handler(commands=['start'])
def send_welcome(message):
  msg = bot.send_message(message.chat.id, "Assalomu alaykum! Ismingizni kiriting:")
  bot.register_next_step_handler(msg, process_first_name)


def process_first_name(message):
  first_name = message.text
  msg = bot.send_message(message.chat.id, "Familiyangizni kiriting:")
  bot.register_next_step_handler(msg, process_last_name, first_name)


def process_last_name(message, first_name):
  last_name = message.text
  markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
  btn = types.KeyboardButton("📞 Telefon raqamni yuborish", request_contact=True)
  markup.add(btn)
  msg = bot.send_message(
      message.chat.id, "Telefon raqamingizni yuboring:", reply_markup=markup
  )
  bot.register_next_step_handler(msg, process_phone, first_name, last_name)


def process_phone(message, first_name, last_name):
  if message.contact:
    phone = message.contact.phone_number
  else:
    phone = message.text

  msg = bot.send_message(
      message.chat.id,
      "Tug'ilgan sanangizni kiriting (Masalan: 2005-05-15):",
      reply_markup=types.ReplyKeyboardRemove(),
  )
  bot.register_next_step_handler(msg, process_birth_date, first_name, last_name, phone)


def process_birth_date(message, first_name, last_name, phone):
  birth_date = message.text
  tg_id = message.from_user.id

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT OR REPLACE INTO users (tg_id, first_name, last_name, phone, birth_date) 
        VALUES (?, ?, ?, ?, ?)
    """,
      (tg_id, first_name, last_name, phone, birth_date),
  )
  conn.commit()
  conn.close()

  bot.send_message(message.chat.id, "Tabriklayman, siz muvaffaqiyatli ro'yxatdan o'tdingiz! ✅")


# Admin buyrug'i (Faqat sizga ishlaydi)
@bot.message_handler(commands=['admin'])
def admin_panel(message):
  # Faqat admin kirishi uchun tekshiruv
  if message.from_user.id != ADMIN_ID:
    bot.send_message(
        message.chat.id, "Kechirasiz, bu buyruq faqat admin uchun! ❌"
    )
    return

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT tg_id, first_name, last_name, phone, payment_status, payment_amount FROM users"
  )
  users = cursor.fetchall()

  # Yillik statistikani hisoblash (Jami tushgan summa)
  cursor.execute("SELECT SUM(payment_amount) FROM users")
  total_yearly_amount = cursor.fetchone()[0] or 0
  conn.close()

  bot.send_message(
      message.chat.id, f"📊 **Yillik umumiy tushum:** {total_yearly_amount} so'm"
  )

  if not users:
    bot.send_message(message.chat.id, "Hozircha mijozlar yo'q.")
    return

  for u in users:
    tg_id, fname, lname, phone, status, amount = u
    text = f"👤 Mijoz: {fname} {lname}\n📞 Raqam: {phone}\n💳 Holat: {status}\n💰 Summa: {amount} so'm"

    markup = types.InlineKeyboardMarkup()
    btn_pay = types.InlineKeyboardButton("✅ To'lov qilish", callback_data=f"ask_amount_{tg_id}")
    btn_delete = types.InlineKeyboardButton("🗑 O'chirish", callback_data=f"delete_user_{tg_id}")
    markup.add(btn_pay, btn_delete)

    bot.send_message(message.chat.id, text, reply_markup=markup)


# To'lov summasini so'rash
@bot.callback_query_handler(func=lambda call: call.data.startswith('ask_amount_'))
def ask_amount(call):
  if call.from_user.id != ADMIN_ID:
    return

  tg_id = call.data.split("_")[2]
  msg = bot.send_message(
      call.message.chat.id, "Iltimos, to'lov summasini kiriting (faqat raqamlar bilan):"
  )
  bot.register_next_step_handler(msg, process_payment_amount, tg_id, call.message.message_id)


def process_payment_amount(message, tg_id, message_id):
  if not message.text.isdigit():
    bot.send_message(
        message.chat.id, "Iltimos, faqat raqam kiriting. Boshqattan /admin buyrug'ini bosing."
    )
    return

  amount = int(message.text)
  tg_id = int(tg_id)
  new_status = "To'langan ✅"

  hozirgi_vaqt_dt = datetime.now()
  hozirgi_vaqt = hozirgi_vaqt_dt.strftime("%Y-%m-%d %H:%M")

  keyingi_oy_dt = add_one_month(hozirgi_vaqt_dt)
  keyingi_vaqt = keyingi_oy_dt.strftime("%Y-%m-%d")

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      """UPDATE users SET payment_status = ?, payment_date = ?, payment_amount = ?, next_payment_date = ? 
                   WHERE tg_id = ?""",
      (new_status, hozirgi_vaqt, amount, keyingi_vaqt, tg_id),
  )
  conn.commit()

  cursor.execute("SELECT first_name, last_name, phone FROM users WHERE tg_id = ?", (tg_id,))
  user = cursor.fetchone()
  name = f"{user[0]} {user[1]}"
  phone = user[2]
  conn.close()

  new_text = f"👤 Mijoz: {name}\n📞 Raqam: {phone}\n💳 Holat: {new_status}\n💰 Summa: {amount} so'm\n🗓 To'lov qilingan sana: {hozirgi_vaqt}\n⏳ Keyingi to'lov sanasi: {keyingi_vaqt}"

  markup = types.InlineKeyboardMarkup()
  btn = types.InlineKeyboardButton("❌ To'lanmagan qilish", callback_data=f"unpay_{tg_id}")
  markup.add(btn)

  bot.edit_message_text(
      chat_id=message.chat.id, message_id=message_id, text=new_text, reply_markup=markup
  )
  bot.send_message(message.chat.id, "To'lov muvaffaqiyatli saqlandi! ✅")

  try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (tg_id,))
    lang = cursor.fetchone()[0]
    conn.close()
    if lang == "uz":
      msg = f"Sizning {amount} so'm to'lovingiz {hozirgi_vaqt} da tasdiqlandi! Rahmat. ✅\n⏳ Keyingi to'lov sanasi: {keyingi_vaqt}"
    else:
      msg = f"Ваша оплата в размере {amount} сум подтверждена в {hozirgi_vaqt}! Спасибо. ✅\n⏳ Следующая оплата: {keyingi_vaqt}"
    bot.send_message(tg_id, msg)
  except:
    pass


# Mijozni bazadan o'chirish (Admin uchun)
@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_user_'))
def delete_user(call):
  if call.from_user.id != ADMIN_ID:
    bot.answer_callback_query(call.id, "Sizda bu huquq yo'q! ❌", show_alert=True)
    return

  tg_id = int(call.data.split("_")[2])

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("DELETE FROM users WHERE tg_id = ?", (tg_id,))
  conn.commit()
  conn.close()

  bot.answer_callback_query(call.id, "Mijoz bazadan o'chirib yuborildi! 🗑")
  bot.edit_message_text(
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      text=call.message.text + "\n\n❌ **USHBU MIJOZ O'CHIRILGAN**",
  )


@bot.callback_query_handler(func=lambda call: call.data.startswith('unpay_'))
def cancel_payment(call):
  if call.from_user.id != ADMIN_ID:
    return

  tg_id = int(call.data.split("_")[1])
  new_status = "Tolanmagan ❌"

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute(
      """UPDATE users SET payment_status = ?, payment_date = NULL, payment_amount = 0, next_payment_date = NULL 
                   WHERE tg_id = ?""",
      (new_status, tg_id),
  )
  conn.commit()

  cursor.execute("SELECT first_name, last_name, phone FROM users WHERE tg_id = ?", (tg_id,))
  user = cursor.fetchone()
  name = f"{user[0]} {user[1]}"
  phone = user[2]
  conn.close()

  new_text = f"👤 Mijoz: {name}\n📞 Raqam: {phone}\n💳 Holat: {new_status}"

  markup = types.InlineKeyboardMarkup()
  btn = types.InlineKeyboardButton("✅ To'lov qilish", callback_data=f"ask_amount_{tg_id}")
  markup.add(btn)

  bot.edit_message_text(
      chat_id=call.message.chat.id,
      message_id=call.message.message_id,
      text=new_text,
      reply_markup=markup,
  )
  bot.answer_callback_query(call.id, "To'lov bekor qilindi!")

  try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (tg_id,))
    lang = cursor.fetchone()[0]
    conn.close()
    msg = "Sizning to'lovingiz bekor qilindi ❌" if lang == "uz" else "Ваша оплата отменена ❌"
    bot.send_message(tg_id, msg)
  except:
    pass


# Flask server (Railway uchun)
app = Flask("")


@app.route("/")
def home():
  return "Xurshida Qandolat Bot ishlayapti! 🚀"


def run_web():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
  t = threading.Thread(target=run_web)
  t.start()
  bot.polling(none_stop=True)
