5.03.2025

start.py -> amazon, teknosa, hepsiburada dosyalarının hepsini aynı anda başlatır. 
YAPILMADI EN SON YAPILACAK.

amazon -> selector +
teknosa -> selector +
hepsiburada -> selector +

telegram.py -> amazon, teknosa, hepsiburada üzerinden gelen istekler buradan kanala yönlendirilir. +

su an yasanan problem:
aynı ürünü tarıyor defalarca. ör: 10 kez + 
aynı ürünü birden fazla kez paylasiyor telegram üzerinden. ör: 5 kez +

12.03.2025

Logdan tespit edilen hata: ERROR - Yanit icerigi: {"ok":false,"error_code":429,"description":"Too Many Requests: retry after 29","parameters":{"retry_after":29}} +

Çözüm: İndirim oranı arttırarak çözülebilir. 
Ürün tespit edildikten sonra kuyruğa alınabilir. Ör: 30saniyelik 

hepsiburada: Sayfada 36 adet ürün bulundu. 
             Toplam 0 ürün işlendi. 0 ürün %25+ indirimli. +

Haftaya Tamamlanması Beklenenler: hepsiburada çözülsün. 

19.03.2025

Hepsiburada tarama başarılı, ürünler taranıyor. Loglara düşüyor. Veritabanına yazılıyor. Sayfa geçişinde hata var.

Telegram arayüzü hazırlansın. (Alternatif olarak websiteme entegre etmeyi deneyebilirim.)

09.04.2025
<<<<<<< HEAD
Telegram arayüz ve kategori özelinde ayırmalar yapıldı fakat henüz bitmedi: telegram_preferences.db

Bot arayüzü bitmiş olsun. 
Sunucu alınacak: https://sunucumfix.com/vds-sunucu-kirala
Bot sürekli calisir hale getirelecek.
Loglardan ip ban yenilen zamanlar tespit edilip ona göre proxy kullanımı gerekecek.

rapor sunumu olacak haftaya
=======

3. Bildirim Gönderme Mantığı
Şimdi, kategori bazlı bildirim gönderme işlevi için telegram_notifier.py dosyasını aşağıdaki gibi güncelleyin:

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import configparser
import logging
import requests
import sqlite3
import time
from typing import Dict, Optional, List

class TelegramNotifier:
    def __init__(self, config_file: str = 'config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        self.bot_token = self.config.get('Telegram', 'bot_token')
        self.chat_id = self.config.get('Telegram', 'chat_id')  # Genel kanal ID'si
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        # Kullanıcı tercihleri veritabanı
        self.db_path = 'telegram_preferences.db'
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
        # Setup logging
        self.logger = logging.getLogger('TelegramNotifier')
        self.logger.setLevel(logging.INFO)
        
        # Add file handler if not exists
        if not self.logger.handlers:
            fh = logging.FileHandler('telegram.log')
            fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(fh)

    def send_product_notification(self, product_data: Dict, marketplace: str, category: str) -> bool:
        """
        Send product notification to Telegram subscribers
        
        Args:
            product_data: Dictionary containing product information
            marketplace: Name of the marketplace (amazon, teknosa, etc.)
            category: Category of the product
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            message = self._format_message(product_data, marketplace)
            
            # 1. Ana kanala gönder
            self._send_message(message, self.chat_id)
            
            # 2. Bu kategoriye abone olan kullanıcılara gönder
            category_id = f"{marketplace.lower()}_{category.lower()}"
            subscribers = self._get_category_subscribers(category_id)
            
            for subscriber in subscribers:
                # Her kullanıcıya özel mesaj gönder
                self._send_message(message, subscriber)
            
            return True
        except Exception as e:
            self.logger.error(f"Error sending notification: {str(e)}")
            return False

    def _get_category_subscribers(self, category_id: str) -> List[int]:
        """Get users subscribed to a specific category"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM user_subscriptions WHERE category_id = ?', (category_id,))
            subscribers = [row[0] for row in cursor.fetchall()]
            conn.close()
            return subscribers
        except Exception as e:
            self.logger.error(f"Error getting subscribers: {str(e)}")
            return []

    def _format_message(self, product_data: Dict, marketplace: str) -> str:
        """Format the message according to product data and marketplace"""
        
        # Base template
        message = f"""🔥 <b>OUTLET FIRSATI!</b> 🔥
📍 <b>{marketplace.upper()}</b>

✅ {product_data.get('name', 'N/A')}
💰 Normal Fiyat: {product_data.get('original_price', 'N/A')} TL
🏷️ İndirimli Fiyat: {product_data.get('discounted_price', 'N/A')} TL
📉 İndirim Oranı: %{product_data.get('discount_rate', 'N/A')}

🔗 <a href="{product_data.get('url', '#')}">Satın almak için tıklayın</a>"""

        return message

    def _send_message(self, message: str, chat_id: str) -> bool:
        """Send message to a specific Telegram chat with retry mechanism"""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    json={
                        'chat_id': chat_id,
                        'text': message,
                        'parse_mode': 'HTML',
                        'disable_web_page_preview': True
                    }
                )
                
                if response.status_code == 200:
                    self.logger.info(f"Telegram bildirimi gönderildi: {chat_id}")
                    return True
                elif response.status_code == 429:  # Too Many Requests
                    retry_after = response.json().get('parameters', {}).get('retry_after', self.retry_delay)
                    self.logger.warning(f"Rate limit exceeded. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                else:
                    self.logger.error(f"Telegram bildirimi başarısız oldu. Status code: {response.status_code}")
                    self.logger.error(f"Yanıt içeriği: {response.text}")
                    
            except Exception as e:
                self.logger.error(f"Error in attempt {attempt + 1}: {str(e)}")
                
            if attempt < self.max_retries - 1:  # Don't sleep on the last attempt
                time.sleep(self.retry_delay)
                
        return False

# Singleton instance
_notifier: Optional[TelegramNotifier] = None

def get_notifier(config_file: str = 'config.ini') -> TelegramNotifier:
    """Get or create the TelegramNotifier singleton instance"""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier(config_file)
    return _notifier



    4. Scraper Kodlarını Güncelleme
Her scraper kodunda (teknosa_scraper.py, hepsiburada_scraper.py, amazon_depo2.py) ürün kategorisini belirlemek ve bu bilgiyi Telegram bildirimine dahil etmek için:

def telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati, kategori='elektronik'):
    """Telegram üzerinden bildirim gönderir."""
    try:
        # Telegram notifier modülünü import et
        from telegram_notifier import get_notifier
        
        # Bildirim verilerini oluştur
        product_data = {
            'name': urun_adi,
            'original_price': sifir_fiyati,
            'discounted_price': outlet_fiyati, 
            'discount_rate': indirim_orani,
            'url': urun_linki
        }
        
        # Notifier'ı al ve bildirimi gönder
        notifier = get_notifier()
        marketplace = 'teknosa'  # veya 'amazon', 'hepsiburada'
        
        # Kullanıcı tercihlerine göre bildirim gönder
        success = notifier.send_product_notification(product_data, marketplace, kategori)
        
        if success:
            # Bildirim durumunu güncelle
            cursor = conn.cursor()
            cursor.execute("UPDATE teknosa_urunler SET bildirildi = 1 WHERE urun_id = ?", (urun_id,))
            conn.commit()
            logging.info(f"Urun {urun_id} icin bildirim gonderildi ve bildirildi=1 olarak isaretlendi.")
            return True
        else:
            logging.error(f"Telegram bildirimi gönderilemedi: {urun_adi}")
            return False
            
    except Exception as e:
        logging.error(f"Telegram bildirimi gönderilirken hata oluştu: {str(e)}")
        return False



5. Kategori Tespiti İşlevi
Ürünlerin kategorisini tespit etmek için her scraper'a kategorize işlevi ekleyin:

def kategorize_urun(urun_adi, urun_aciklamasi=''):
    """Ürünün kategorisini belirler."""
    # Basit anahtar kelime eşleştirme
    urun_bilgisi = (urun_adi + ' ' + urun_aciklamasi).lower()
    
    # Telefon/Tablet kategorisi
    if any(keyword in urun_bilgisi for keyword in ['telefon', 'cep telefonu', 'tablet', 'ipad', 'iphone', 'samsung', 'xiaomi', 'huawei']):
        return 'telefon'
    
    # Beyaz Eşya kategorisi
    elif any(keyword in urun_bilgisi for keyword in ['buzdolabı', 'çamaşır', 'bulaşık', 'fırın', 'ocak', 'davlumbaz', 'derin dondurucu']):
        return 'beyaz_esya'
    
    # Bilgisayar kategorisi
    elif any(keyword in urun_bilgisi for keyword in ['laptop', 'bilgisayar', 'pc', 'notebook', 'ram', 'ssd', 'anakart']):
        return 'bilgisayar'
    
    # Televizyon ve Ses Sistemleri
    elif any(keyword in urun_bilgisi for keyword in ['tv', 'televizyon', 'hoparlör', 'kulaklık', 'ses sistemi', 'soundbar']):
        return 'tv_ses'
    
    # Küçük Ev Aletleri
    elif any(keyword in urun_bilgisi for keyword in ['mikser', 'blender', 'tost', 'ütü', 'süpürge', 'kahve', 'çay', 'hava temizleyici']):
        return 'kucuk_ev_aletleri'
    
    # Giyim
    elif any(keyword in urun_bilgisi for keyword in ['pantolon', 'gömlek', 'elbise', 'ayakkabı', 'ceket', 'mont', 'tişört']):
        return 'giyim'
    
    # Kitap ve Müzik
    elif any(keyword in urun_bilgisi for keyword in ['kitap', 'müzik', 'roman', 'cd', 'plak']):
        return 'kitap_muzik'
    
    # Kozmetik
    elif any(keyword in urun_bilgisi for keyword in ['parfüm', 'makyaj', 'cilt bakım', 'saç', 'şampuan']):
        return 'kozmetik'
    
    # Varsayılan kategori
    else:
        return 'elektronik'


6. Scraper Kodlarını Entegre Etme
Bu kategorileme ve bildirim gönderme işlevlerini büyük scraper kodunuza entegre edin, örneğin:

# Ürün işleme kısmında
kategori = kategorize_urun(urun_adi, urun_aciklamasi)

# Bildirim gönderme kısmında
telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki, 
                         indirim_orani, sifir_fiyati, outlet_fiyati, 
                         kategori=kategori)
>>>>>>> origin/main
