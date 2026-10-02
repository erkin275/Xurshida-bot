import telebot
from telebot import types
import sqlite3
from datetime import datetime
import calendar

# O'zingizning bot tokeningizni va admin ID'sini kiriting
TOKEN = '8707409506:AAHaQhU41RKwQbCvliaBGKWXXhYd7wSOa6I'
ADMIN_ID = 6766950408 # O'zingizning Telegram ID'ingiz

bot = telebot.TeleBot(TOKEN)

# Baza yaratish
conn = sqlite3.connect('xurshida_qandolat.db', check_same_thread=False)
cursor = conn.cursor()

# Jadvalni yangilash
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        lang TEXT,
        first_name TEXT,
        last_name TEXT,
        phone TEXT,
        payment_status TEXT DEFAULT 'Tolanmagan ❌',
        payment_date TEXT,
        payment_amount INTEGER DEFAULT 0,
        next_payment_date TEXT
    )
''')

# Agar baza avval yaratilgan bo'lsa va ustunlar yo'q bo'lsa, ularni qo'shish
try:
    cursor.execute("ALTER TABLE users ADD COLUMN payment_date TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN payment_amount INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE users ADD COLUMN next_payment_date TEXT")
except sqlite3.OperationalError:
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN next_payment_date TEXT")
    except sqlite3.OperationalError:
        pass

conn.commit()

# Bir oy qo'shish funksiyasi
def add_one_month(dt):
    month = dt.month
    year = dt.year
    day = dt.day
    if month == 12:
        month = 1
        year += 1
    else:
        month += 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(day, max_day)
    return dt.replace(year=year, month=month, day=day)

# Til tanlash
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("🇺🇿 O'zbekcha", "🇷🇺 Русский")
    bot.send_message(message.chat.id, "Assalomu alaykum! \"Xurshida Qandolat O.K\" botiga xush kelibsiz.\nTilni tanlang / Выберите язык:", reply_markup=markup)

# Tilni saqlash va ism so'rash
@bot.message_handler(func=lambda message: message.text in ["🇺🇿 O'zbekcha", "🇷🇺 Русский"])
def set_language(message):
    lang = "uz" if message.text == "🇺🇿 O'zbekcha" else "ru"
    
    cursor.execute("INSERT OR IGNORE INTO users (tg_id, lang) VALUES (?, ?)", (message.chat.id, lang))
    cursor.execute("UPDATE users SET lang = ? WHERE tg_id = ?", (lang, message.chat.id))
    conn.commit()
    
    text = "Ismingizni kiriting:" if lang == "uz" else "Введите ваше имя:"
    msg = bot.send_message(message.chat.id, text, reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_first_name)

def process_first_name(message):
    first_name = message.text
    cursor.execute("UPDATE users SET first_name = ? WHERE tg_id = ?", (first_name, message.chat.id))
    conn.commit()
    
    cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (message.chat.id,))
    lang = cursor.fetchone()[0]
    
    text = "Familiyangizni kiriting:" if lang == "uz" else "Введите вашу фамилию:"
    msg = bot.send_message(message.chat.id, text)
    bot.register_next_step_handler(msg, process_last_name)

def process_last_name(message):
    last_name = message.text
    cursor.execute("UPDATE users SET last_name = ? WHERE tg_id = ?", (last_name, message.chat.id))
    conn.commit()
    
    cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (message.chat.id,))
    lang = cursor.fetchone()[0]
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn_text = "📞 Raqamni yuborish" if lang == "uz" else "📞 Отправить номер"
    btn = types.KeyboardButton(text=btn_text, request_contact=True)
    markup.add(btn)
    
    text = "Iltimos, telefon raqamingizni pastdagi tugma orqali yuboring:" if lang == "uz" else "Отправьте свой номер через кнопку ниже:"
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(content_types=['contact'])
def process_phone(message):
    phone = message.contact.phone_number
    cursor.execute("UPDATE users SET phone = ? WHERE tg_id = ?", (phone, message.chat.id))
    conn.commit()
    
    cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (message.chat.id,))
    lang = cursor.fetchone()[0]
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn_text = "💼 Mening hisobim" if lang == "uz" else "💼 Мой счет"
    markup.add(btn_text)
    
    text = "Ro'yxatdan muvaffaqiyatli o'tdingiz!" if lang == "uz" else "Вы успешно зарегистрированы!"
    bot.send_message(message.chat.id, text, reply_markup=markup)

# Mijoz o'z hisobini ko'rishi
@bot.message_handler(func=lambda message: message.text in ["💼 Mening hisobim", "💼 Мой счет"])
def my_account(message):
    cursor.execute("SELECT first_name, last_name, payment_status, payment_date, payment_amount, next_payment_date, lang FROM users WHERE tg_id = ?", (message.chat.id,))
    user = cursor.fetchone()
    
    if user:
        first_name, last_name, status, p_date, p_amount, next_date, lang = user
        date_str = f"\n🗓 Oxirgi to'lov: {p_date}" if p_date else ""
        next_date_str = f"\n⏳ Keyingi to'lov sanasi: {next_date}" if next_date else ""
        amount_str = f"\n💰 Summa: {p_amount} so'm" if p_amount > 0 else ""
        
        if lang == "uz":
            text = f"🏢 \"Xurshida Qandolat O.K\"\n👤 Mijoz: {first_name} {last_name}\n💳 To'lov holati: {status}{amount_str}{date_str}{next_date_str}"
        else:
            text = f"🏢 \"Xurshida Qandolat O.K\"\n👤 Клиент: {first_name} {last_name}\n💳 Статус оплаты: {status}{amount_str}{date_str}\n⏳ Следующая оплата: {next_date}"
        bot.send_message(message.chat.id, text)

# Admin paneli
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.chat.id == ADMIN_ID:
        cursor.execute("SELECT tg_id, first_name, last_name, phone, payment_status, payment_date, payment_amount, next_payment_date FROM users")
        users = cursor.fetchall()
        
        if not users:
            bot.send_message(message.chat.id, "Mijozlar ro'yxati hozircha bo'sh.")
            return
            
        bot.send_message(message.chat.id, "🏢 \"Xurshida Qandolat O.K\" Mijozlari:")
        
        for u in users:
            tg_id = u[0]
            name = f"{u[1]} {u[2]}"
            phone = u[3]
            status = u[4]
            p_date = u[5]
            p_amount = u[6]
            next_date = u[7]
            
            date_str = f"\n🗓 To'lov qilingan sana: {p_date}" if p_date else ""
            next_date_str = f"\n⏳ Keyingi to'lov sanasi: {next_date}" if next_date else ""
            amount_str = f"\n💰 Summa: {p_amount} so'm" if p_amount > 0 else ""
            
            text = f"👤 Mijoz: {name}\n📞 Raqam: {phone}\n💳 Holat: {status}{amount_str}{date_str}{next_date_str}"
            
            markup = types.InlineKeyboardMarkup()
            if "❌" in status:
                btn = types.InlineKeyboardButton("✅ To'lov qilish", callback_data=f"ask_amount_{tg_id}")
            else:
                btn = types.InlineKeyboardButton("❌ To'lanmagan qilish", callback_data=f"unpay_{tg_id}")
            markup.add(btn)
            
            bot.send_message(message.chat.id, text, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Kechirasiz, sizda admin huquqi yo'q!")

# Oylik hisobot chiqarish (Admin uchun)
@bot.message_handler(commands=['hisobot'])
def oylik_hisobot(message):
    if message.chat.id == ADMIN_ID:
        shu_oy = datetime.now().strftime("%Y-%m")
        cursor.execute("SELECT SUM(payment_amount) FROM users WHERE payment_status = 'To\'langan ✅' AND payment_date LIKE ?", (f"{shu_oy}%",))
        jami_tushum = cursor.fetchone()[0]
        
        if jami_tushum is None:
            jami_tushum = 0
            
        xabar = f"📊 <b>{datetime.now().strftime('%B, %Y')} uchun umumiy tushum:</b>\n💰 {jami_tushum:,} so'm".replace(',', ' ')
        bot.send_message(message.chat.id, xabar, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "Kechirasiz, sizda admin huquqi yo'q!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ask_amount_'))
def ask_amount(call):
    tg_id = call.data.split('_')[2]
    msg = bot.send_message(call.message.chat.id, "Iltimos, to'lov summasini kiriting (faqat raqamlar bilan):")
    bot.register_next_step_handler(msg, process_payment_amount, tg_id, call.message.message_id)

def process_payment_amount(message, tg_id, message_id):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Iltimos, faqat raqam kiriting. Boshqattan /admin buyrug'ini bosing.")
        return
        
    amount = int(message.text)
    tg_id = int(tg_id)
    new_status = "To'langan ✅"
    
    hozirgi_vaqt_dt = datetime.now()
    hozirgi_vaqt = hozirgi_vaqt_dt.strftime("%Y-%m-%d %H:%M")
    
    keyingi_oy_dt = add_one_month(hozirgi_vaqt_dt)
    keyingi_vaqt = keyingi_oy_dt.strftime("%Y-%m-%d")
    
    cursor.execute("UPDATE users SET payment_status = ?, payment_date = ?, payment_amount = ?, next_payment_date = ? WHERE tg_id = ?", (new_status, hozirgi_vaqt, amount, keyingi_vaqt, tg_id))
    conn.commit()
    
    cursor.execute("SELECT first_name, last_name, phone FROM users WHERE tg_id = ?", (tg_id,))
    user = cursor.fetchone()
    name = f"{user[0]} {user[1]}"
    phone = user[2]
    
    new_text = f"👤 Mijoz: {name}\n📞 Raqam: {phone}\n💳 Holat: {new_status}\n💰 Summa: {amount} so'm\n🗓 To'lov qilingan sana: {hozirgi_vaqt}\n⏳ Keyingi to'lov sanasi: {keyingi_vaqt}"
    
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("❌ To'lanmagan qilish", callback_data=f"unpay_{tg_id}")
    markup.add(btn)
    
    bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=new_text, reply_markup=markup)
    bot.send_message(message.chat.id, "To'lov muvaffaqiyatli saqlandi! ✅")
    
    try:
        cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (tg_id,))
        lang = cursor.fetchone()[0]
        if lang == "uz":
            msg = f"Sizning {amount} so'm to'lovingiz {hozirgi_vaqt} da tasdiqlandi! Rahmat. ✅\n⏳ Keyingi to'lov sanasi: {keyingi_vaqt}"
        else:
            msg = f"Ваша оплата в размере {amount} сум подтверждена в {hozirgi_vaqt}! Спасибо. ✅\n⏳ Следующая оплата: {keyingi_vaqt}"
        bot.send_message(tg_id, msg)
    except:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith('unpay_'))
def cancel_payment(call):
    tg_id = int(call.data.split('_')[1])
    new_status = "Tolanmagan ❌"
    
    cursor.execute("UPDATE users SET payment_status = ?, payment_date = NULL, payment_amount = 0, next_payment_date = NULL WHERE tg_id = ?", (new_status, tg_id))
    conn.commit()
    
    cursor.execute("SELECT first_name, last_name, phone FROM users WHERE tg_id = ?", (tg_id,))
    user = cursor.fetchone()
    name = f"{user[0]} {user[1]}"
    phone = user[2]
    
    new_text = f"👤 Mijoz: {name}\n📞 Raqam: {phone}\n💳 Holat: {new_status}"
    
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("✅ To'lov qilish", callback_data=f"ask_amount_{tg_id}")
    markup.add(btn)
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=new_text, reply_markup=markup)
    bot.answer_callback_query(call.id, "To'lov bekor qilindi!")
    
    try:
        cursor.execute("SELECT lang FROM users WHERE tg_id = ?", (tg_id,))
        lang = cursor.fetchone()[0]
        msg = "Sizning to'lovingiz bekor qilindi ❌" if lang == "uz" else "Ваша оплата отменена ❌"
        bot.send_message(tg_id, msg)
    except:
        pass

# Botni uzluksiz ishga tushirish
if __name__ == "__main__":
    bot.polling(none_stop=True)
  
