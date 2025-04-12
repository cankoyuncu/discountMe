#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
import configparser

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='telegram_bot.log'
)
logger = logging.getLogger(__name__)

# Veritabanı yolu
DB_PATH = 'telegram_preferences.db'

# Kategori listesi
CATEGORIES = {
    'teknosa_elektronik': 'Teknosa - Elektronik',
<<<<<<< HEAD
    'amazon_elektronik': 'Amazon - Elektronik',
    'hepsiburada_elektronik': 'Hepsiburada - Elektronik',
    'amazon_moda': 'Amazon - Moda',
    'hepsiburada_moda': 'Hepsiburada - Moda'
=======
    'teknosa_beyaz_esya': 'Teknosa - Beyaz Eşya',
    'teknosa_telefon': 'Teknosa - Telefon/Tablet',
    'amazon_elektronik': 'Amazon - Elektronik',
    'amazon_giyim': 'Amazon - Giyim',
    'amazon_kitap': 'Amazon - Kitap & Müzik',
    'hepsiburada_elektronik': 'Hepsiburada - Elektronik',
    'hepsiburada_ev': 'Hepsiburada - Ev & Yaşam',
    'hepsiburada_kozmetik': 'Hepsiburada - Kozmetik'
>>>>>>> origin/main
}

# Durum kodları
SELECTING_CATEGORIES, SUBSCRIBE, UNSUBSCRIBE = range(3)

def setup_database():
    """Veritabanı bağlantısını kurar ve gerekli tabloları oluşturur."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Kullanıcılar tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        username TEXT,
        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Kategoriler tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS categories (
        category_id TEXT PRIMARY KEY,
        name TEXT
    )
    ''')
    
    # Kullanıcı abonelikleri tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_subscriptions (
        user_id INTEGER,
        category_id TEXT,
        subscription_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, category_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
    )
    ''')
    
    # Kategorileri ekle
    for category_id, category_name in CATEGORIES.items():
        cursor.execute('INSERT OR IGNORE INTO categories (category_id, name) VALUES (?, ?)',
                      (category_id, category_name))
    
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Karşılama mesajı ve kullanıcı kaydı."""
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    username = user.username
    
    # Kullanıcıyı veritabanına kaydet
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
    VALUES (?, ?, ?, ?)
    ''', (user_id, first_name, last_name, username))
    conn.commit()
    conn.close()
    
    welcome_text = (
        f"Merhaba {first_name}! 👋\n\n"
        f"İndirim Bildirim Botuna hoş geldiniz. Bu bot, seçtiğiniz kategorilerdeki indirimli ürünlerden haberdar olmanızı sağlar.\n\n"
        f"Aşağıdaki komutları kullanabilirsiniz:\n"
        f"/categories - Mevcut kategorileri göster\n"
        f"/subscribe - Kategorilere abone ol\n"
        f"/unsubscribe - Kategorilerden aboneliği kaldır\n"
        f"/mysubscriptions - Abone olduğum kategorileri göster\n"
        f"/help - Yardım mesajı"
    )
    
    await update.message.reply_text(welcome_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yardım mesajı gönderir."""
    help_text = (
        "📱 *İndirim Bildirim Botu Yardım* 📱\n\n"
        "Bu bot ile çeşitli kategorilerdeki indirimli ürünlerden haberdar olabilirsiniz.\n\n"
        "*Komut Listesi:*\n"
        "/start - Karşılama mesajı\n"
        "/categories - Mevcut kategorileri göster\n"
        "/subscribe - Kategorilere abone ol\n"
        "/unsubscribe - Kategorilerden aboneliği kaldır\n"
        "/mysubscriptions - Abone olduğum kategorileri göster\n"
        "/help - Bu yardım mesajını göster\n\n"
        "Daha fazla bilgi için: @kullanici_adi" # Kendi Telegram kullanıcı adınızı ekleyin
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mevcut kategorileri listeler."""
    categories_text = "📋 *Mevcut Kategoriler* 📋\n\n"
    
    for category_id, category_name in CATEGORIES.items():
        categories_text += f"• {category_name}\n"
    
    categories_text += "\nAbone olmak için /subscribe komutunu kullanabilirsiniz."
    
    await update.message.reply_text(categories_text, parse_mode='Markdown')

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kategori abonelik sürecini başlatır."""
    user_id = update.effective_user.id
    
    # Kullanıcının mevcut aboneliklerini al
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT category_id FROM user_subscriptions WHERE user_id = ?', (user_id,))
    subscribed_categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    # Abone olunmayan kategorileri içeren klavye oluştur
    keyboard = []
    for category_id, category_name in CATEGORIES.items():
        if category_id not in subscribed_categories:
            keyboard.append([InlineKeyboardButton(
                f"{category_name}", callback_data=f"subscribe_{category_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("✅ Bitir", callback_data="subscribe_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Lütfen abone olmak istediğiniz kategorileri seçin:",
        reply_markup=reply_markup
    )
    
    return SUBSCRIBE

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kategori abonelik iptal sürecini başlatır."""
    user_id = update.effective_user.id
    
    # Kullanıcının mevcut aboneliklerini al
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT c.category_id, c.name 
    FROM user_subscriptions us
    JOIN categories c ON us.category_id = c.category_id
    WHERE us.user_id = ?
    ''', (user_id,))
    subscriptions = cursor.fetchall()
    conn.close()
    
    if not subscriptions:
        await update.message.reply_text("Henüz hiçbir kategoriye abone değilsiniz.")
        return ConversationHandler.END
    
    # Abone olunan kategorileri içeren klavye oluştur
    keyboard = []
    for category_id, category_name in subscriptions:
        keyboard.append([InlineKeyboardButton(
            f"{category_name}", callback_data=f"unsubscribe_{category_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("✅ Bitir", callback_data="unsubscribe_done")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Aboneliğini iptal etmek istediğiniz kategorileri seçin:",
        reply_markup=reply_markup
    )
    
    return UNSUBSCRIBE

async def my_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcının abone olduğu kategorileri gösterir."""
    user_id = update.effective_user.id
    
    # Kullanıcının aboneliklerini al
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT c.category_id, c.name 
    FROM user_subscriptions us
    JOIN categories c ON us.category_id = c.category_id
    WHERE us.user_id = ?
    ''', (user_id,))
    subscriptions = cursor.fetchall()
    conn.close()
    
    if not subscriptions:
        await update.message.reply_text("Henüz hiçbir kategoriye abone değilsiniz. Abone olmak için /subscribe komutunu kullanabilirsiniz.")
        return
    
    subscriptions_text = "🔔 *Abone Olduğum Kategoriler* 🔔\n\n"
    for _, category_name in subscriptions:
        subscriptions_text += f"• {category_name}\n"
    
    subscriptions_text += "\nAboneliği iptal etmek için /unsubscribe komutunu kullanabilirsiniz."
    
    await update.message.reply_text(subscriptions_text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buton tıklamalarını işler."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    # Abone ol
    if data.startswith("subscribe_"):
        category_id = data.replace("subscribe_", "")
        
        if category_id == "done":
            await query.edit_message_text("Kategori seçiminiz kaydedilmiştir. Yeni indirimler için bildirim alacaksınız!")
            return ConversationHandler.END
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT OR IGNORE INTO user_subscriptions (user_id, category_id) VALUES (?, ?)',
                          (user_id, category_id))
            conn.commit()
            
            # Mevcut ve aboneliği olmayan kategorileri al
            cursor.execute('SELECT category_id FROM user_subscriptions WHERE user_id = ?', (user_id,))
            subscribed_categories = [row[0] for row in cursor.fetchall()]
            
            # Yeni klavye oluştur
            keyboard = []
            for cat_id, cat_name in CATEGORIES.items():
                if cat_id not in subscribed_categories:
                    keyboard.append([InlineKeyboardButton(f"{cat_name}", callback_data=f"subscribe_{cat_id}")])
            
            keyboard.append([InlineKeyboardButton("✅ Bitir", callback_data="subscribe_done")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Kategori adını al
            cursor.execute('SELECT name FROM categories WHERE category_id = ?', (category_id,))
            category_name = cursor.fetchone()[0]
            
            await query.edit_message_text(
                f"'{category_name}' kategorisine abone oldunuz.\n\nBaşka kategori seçebilir veya Bitir'e tıklayabilirsiniz:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Abonelik hatası: {str(e)}")
            await query.edit_message_text("Bir hata oluştu. Lütfen daha sonra tekrar deneyin.")
        finally:
            conn.close()
    
    # Abonelik iptali
    elif data.startswith("unsubscribe_"):
        category_id = data.replace("unsubscribe_", "")
        
        if category_id == "done":
            await query.edit_message_text("Abonelik iptali tamamlandı.")
            return ConversationHandler.END
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM user_subscriptions WHERE user_id = ? AND category_id = ?',
                          (user_id, category_id))
            conn.commit()
            
            # Kalan aboneliklerini al
            cursor.execute('''
            SELECT c.category_id, c.name 
            FROM user_subscriptions us
            JOIN categories c ON us.category_id = c.category_id
            WHERE us.user_id = ?
            ''', (user_id,))
            subscriptions = cursor.fetchall()
            
            # Kategori adını al
            cursor.execute('SELECT name FROM categories WHERE category_id = ?', (category_id,))
            category_name = cursor.fetchone()[0]
            
            if not subscriptions:
                await query.edit_message_text(f"'{category_name}' kategorisi abonelikten çıkarıldı. Artık hiçbir kategoriye abone değilsiniz.")
                return ConversationHandler.END
            
            # Yeni klavye oluştur
            keyboard = []
            for cat_id, cat_name in subscriptions:
                keyboard.append([InlineKeyboardButton(f"{cat_name}", callback_data=f"unsubscribe_{cat_id}")])
            
            keyboard.append([InlineKeyboardButton("✅ Bitir", callback_data="unsubscribe_done")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"'{category_name}' kategorisi abonelikten çıkarıldı.\n\nBaşka kategori seçebilir veya Bitir'e tıklayabilirsiniz:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Abonelik iptali hatası: {str(e)}")
            await query.edit_message_text("Bir hata oluştu. Lütfen daha sonra tekrar deneyin.")
        finally:
            conn.close()

def main():
    """Bot başlatma fonksiyonu."""
    # Veritabanını kur
    setup_database()
    
    # Config dosyasından token oku
    config = configparser.ConfigParser()
    config.read('config.ini')
    token = config['Telegram']['bot_token']
    
    # Bot oluştur
    application = Application.builder().token(token).build()
    
    # Komut işleyicileri
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("categories", show_categories))
    application.add_handler(CommandHandler("mysubscriptions", my_subscriptions))
    
    # Abonelik işleme
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("subscribe", subscribe),
            CommandHandler("unsubscribe", unsubscribe)
        ],
        states={
            SUBSCRIBE: [CallbackQueryHandler(button_callback, pattern=r"^subscribe_")],
            UNSUBSCRIBE: [CallbackQueryHandler(button_callback, pattern=r"^unsubscribe_")]
        },
        fallbacks=[MessageHandler(filters.TEXT, help_command)]
    )
    
    application.add_handler(conv_handler)
    
    # Buton tıklama işleyicisi
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Botu başlat
    application.run_polling()

if __name__ == '__main__':
    main()