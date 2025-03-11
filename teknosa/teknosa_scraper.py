import os
import sys
import time
import logging
import sqlite3
import requests
import configparser
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Teknosa klasör yolunu tanımla
TEKNOSA_DIR = os.path.dirname(os.path.abspath(__file__))

# Konfigürasyon dosyasını yükle
config = configparser.ConfigParser(interpolation=None)  # İnterpolasyonu kapat
config_path = os.path.join(TEKNOSA_DIR, 'config.ini')
if not os.path.exists(config_path):
    # Eğer config dosyası yoksa, örnek bir config oluştur
    config['DATABASE'] = {'Path': os.path.join(TEKNOSA_DIR, 'teknosa_products.db')}
    config['LOGGING'] = {'LogFile': os.path.join(TEKNOSA_DIR, 'teknosa_scraper.log'), 'Level': 'INFO'}
    config['TELEGRAM'] = {'BotToken': 'YOUR_BOT_TOKEN', 'ChatID': 'YOUR_CHAT_ID'}
    config['URLS'] = {
        'TeknosaOutlet': 'https://www.teknosa.com/outlet?sort=newProduct-desc&s=%3AbestSellerPoint-desc'
    }
    
    with open(config_path, 'w') as configfile:
        config.write(configfile)
else:
    config.read(config_path)

def setup_logging():
    """Log yapılandırmasını ayarlar."""
    log_file = config['LOGGING'].get('LogFile', os.path.join(TEKNOSA_DIR, 'teknosa_scraper.log'))
    log_level = config['LOGGING'].get('Level', 'INFO')
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        filename=log_file,
        filemode='a'
    )
    
    # Konsol çıktısı için handler ekle
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, log_level))
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    
    return logging.getLogger(__name__)

def setup_db():
    """Veritabani baglantisini kurar ve gerekli tabloyu olusturur."""
    db_path = config['DATABASE']['Path']
    # Klasör yolu DB dosyasında belirtilmediyse, teknosa klasörü altında oluştur
    if not os.path.isabs(db_path):
        db_path = os.path.join(TEKNOSA_DIR, db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ürünler tablosunu oluştur (eğer yoksa)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teknosa_urunler (
        urun_id TEXT PRIMARY KEY,
        urun_adi TEXT,
        urun_linki TEXT,
        indirim_orani REAL,
        sifir_fiyati REAL,
        outlet_fiyati REAL,
        bildirildi INTEGER DEFAULT 0,
        tarih TEXT
    )
    """)
    
    conn.commit()
    return conn

def setup_driver():
    """Selenium WebDriver'i yapilandirir ve dondurur."""
    options = Options()
    options.add_argument("--headless")  # Başsız mod
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    return driver

def clean_price(price_str):
    """Fiyat stringini temizleyip float değere dönüştürür."""
    if not price_str:
        return 0.0
    
    # Türkçe fiyat formatı: "1.234,56 TL"
    price_str = price_str.replace("TL", "").strip()
    price_str = price_str.replace(".", "")  # Binlik ayracı
    price_str = price_str.replace(",", ".")  # Ondalık ayracı
    
    try:
        return float(price_str)
    except ValueError:
        logging.error(f"Fiyat dönüştürülemedi: {price_str}")
        return 0.0

def telegram_bildirim_gonder(urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati):
    """Telegram üzerinden bildirim gönderir."""
    bot_token = config['TELEGRAM']['BotToken']
    chat_id = config['TELEGRAM']['ChatID']
    
    # Bot token ve chat ID kontrolü
    if bot_token == 'YOUR_BOT_TOKEN' or chat_id == 'YOUR_CHAT_ID':
        logging.warning("Gecerli Telegram bot token ve chat ID ayarlanmamis. Bildirim gonderilemiyor.")
        return False
    
    # İndirim miktarını hesapla
    indirim_miktari = sifir_fiyati - outlet_fiyati
    
    # Mesaj içeriği
    message = f"""
🔥 <b>OUTLET FIRSATI!</b> 🔥
✅ {urun_adi}

💰 <b>Outlet Fiyatı:</b> {outlet_fiyati:.2f} TL
📌 <b>Sıfır Fiyatı:</b> {sifir_fiyati:.2f} TL
🏷️ <b>Indirim:</b> %{indirim_orani} ({indirim_miktari:.2f} TL)

🔗 <a href="{urun_linki}">Satin almak icin tiklayin</a>
"""
    
    # Telegram API URL'si
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Hata ayıklama için log
    logging.info(f"Telegram API URL: {url}")
    logging.info(f"Chat ID: {chat_id}")
    
    # İstek parametreleri
    params = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    # Yeniden deneme parametreleri
    max_retries = 3
    retry_count = 0
    
    # Telegram'a mesaj göndermeyi dene
    while retry_count < max_retries:
        try:
            response = requests.post(url, params=params)
            if response.status_code == 200:
                logging.info(f"Telegram bildirimi gonderildi: {urun_adi}")
                return True
            else:
                logging.error(f"Telegram bildirimi basariiz oldu. Status code: {response.status_code}")
                logging.error(f"Yanit icerigi: {response.text}")
                retry_count += 1
                time.sleep(2)
        except Exception as e:
            logging.error(f"Telegram bildirimi gönderilirken hata oluştu: {str(e)}")
            retry_count += 1
            time.sleep(2)
    
    return False

def urun_kaydet(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati):
    """Urunu veritabanina kaydeder veya gunceller."""
    try:
        cursor = conn.cursor()
        tarih = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Önce ürünün veritabanında olup olmadığını kontrol et
        cursor.execute("SELECT * FROM teknosa_urunler WHERE urun_id = ?", (urun_id,))
        existing_product = cursor.fetchone()
        
        if existing_product:
            # Fiyat değişikliği varsa güncelle ve bildirildi durumunu sıfırla
            if existing_product[5] != outlet_fiyati or existing_product[3] != indirim_orani:
                cursor.execute("""
                UPDATE teknosa_urunler 
                SET outlet_fiyati = ?, indirim_orani = ?, tarih = ?, bildirildi = ? 
                WHERE urun_id = ?
                """, (outlet_fiyati, indirim_orani, tarih, 0 if indirim_orani >= 25 else 1, urun_id))
                
                logging.info(f"Urun fiyati guncellendi: {urun_adi}, Eski: {existing_product[5]}, Yeni: {outlet_fiyati}")
            else:
                # Fiyat değişmediyse sadece tarihi güncelle
                cursor.execute("""
                UPDATE teknosa_urunler 
                SET tarih = ? 
                WHERE urun_id = ?
                """, (tarih, urun_id))
        else:
            # Yeni ürün, ekle - indirim oranı %25+ ise bildirildi=0, değilse bildirildi=1
            bildirildi_degeri = 0 if indirim_orani >= 25 else 1
            cursor.execute("""
            INSERT INTO teknosa_urunler (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati, bildirildi, tarih)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati, bildirildi_degeri, tarih))
            logging.info(f"Yeni urun kaydedildi: {urun_adi}")
        
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Urun kaydedilirken hata oluştu: {str(e)}")
        return False

def bildirim_durumu_guncelle(conn, urun_id):
    """Urunun bildirim durumunu günceller."""
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE teknosa_urunler SET bildirildi = 1 WHERE urun_id = ?", (urun_id,))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Bildirim durumu guncellenirken hata oluştu: {str(e)}")
        return False

def scan_teknosa_outlet():
    """Teknosa outlet sayfasini tarar ve urunleri isler."""
    logger = logging.getLogger(__name__)
    logger.info("Teknosa outlet taramasi baslatiliyor...")
    
    conn = setup_db()
    driver = setup_driver()
    
    try:
        # Teknosa outlet URL'sini yükle
        url = config['URLS']['TeknosaOutlet']
        driver.get(url)
        time.sleep(5)  # Sayfanın yüklenmesini bekle
        
        # Sayfa yüklenmesini bekle
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".prd-title"))
        )
        
        urun_sayisi = 0
        indirim_urun_sayisi = 0
        sayfa_no = 1
        max_sayfa = 10  # Maksimum taranacak sayfa sayısı
        
        while sayfa_no <= max_sayfa:
            logger.info(f"Sayfa {sayfa_no} taraniyor...")
            
            # Sayfadaki tüm ürün elementlerini bul
            urunler = driver.find_elements(By.CSS_SELECTOR, "#product-item")
            logger.info(f"Sayfa {sayfa_no}'de {len(urunler)} adet ürün bulundu.")
            
            if not urunler:
                logger.warning(f"Sayfa {sayfa_no}'de ürün bulunamadı, tarama sonlandırılıyor.")
                break
            
            # Her ürünü işle
            for urun in urunler:
                try:
                    # Ürün ID'sini al
                    urun_id = urun.get_attribute('data-product-id')
                    if not urun_id:
                        logger.warning("Urun ID'si bulunamadı, geçiliyor...")
                        continue
                    
                    logger.info(f"Islenen urun ID: {urun_id}")
                    
                    # Ürün adını al
                    try:
                        urun_adi_element = urun.find_element(By.CSS_SELECTOR, "h3.prd-title")
                        urun_adi = urun_adi_element.text.strip()
                    except NoSuchElementException:
                        logger.warning(f"Urun adi bulunamadı - ID: {urun_id}")
                        urun_adi = f"Teknosa Urun #{urun_id}"
                    
                    # Ürün linkini al
                    try:
                        urun_linki_element = urun.find_element(By.CSS_SELECTOR, "a.prd-link")
                        urun_linki_path = urun_linki_element.get_attribute('href')
                        if (urun_linki_path):
                            urun_linki = urun_linki_path
                        else:
                            # href yoksa data attribute'a bak
                            urun_linki = "https://www.teknosa.com" + urun.get_attribute('data-product-url')
                    except NoSuchElementException:
                        logger.warning(f"Urun linki bulunamadi - ID: {urun_id}")
                        # data-product-url attribute'unu kullan
                        urun_linki = "https://www.teknosa.com" + urun.get_attribute('data-product-url')
                    
                    # İndirim oranını al (HTML'den doğru selector)
                    try:
                        indirim_orani_element = urun.find_element(By.CSS_SELECTOR, "div.prd-discount")
                        indirim_orani_text = indirim_orani_element.text.strip().replace("%", "")
                        indirim_orani = float(indirim_orani_text)
                    except (NoSuchElementException, ValueError):
                        # HTML'den data attribute'u kullan
                        indirim_orani = float(urun.get_attribute('data-product-discount-rate') or 0)
                        logger.info(f"Indirim orani data attribute'dan alindi: {indirim_orani}")
                    
                    # Sıfır fiyatını al
                    try:
                        sifir_fiyati_element = urun.find_element(By.CSS_SELECTOR, "span.prc-first")
                        sifir_fiyati_text = sifir_fiyati_element.text.strip()
                        sifir_fiyati = clean_price(sifir_fiyati_text)
                    except NoSuchElementException:
                        # data attribute'u kullan
                        sifir_fiyati = float(urun.get_attribute('data-product-actual-price') or 0)
                        logger.info(f"Sifir fiyati data attribute'dan alindi: {sifir_fiyati}")
                    
                    # Outlet fiyatını al
                    try:
                        outlet_fiyati_element = urun.find_element(By.CSS_SELECTOR, "span.prc-last")
                        outlet_fiyati_text = outlet_fiyati_element.text.strip()
                        outlet_fiyati = clean_price(outlet_fiyati_text)
                    except NoSuchElementException:
                        # data attribute'u kullan
                        outlet_fiyati = float(urun.get_attribute('data-product-discounted-price') or 0)
                        logger.info(f"Outlet fiyati data attribute'dan alindi: {outlet_fiyati}")
                    
                    logger.info(f"Urun: {urun_adi}, Indirim: %{indirim_orani}, Sifir Fiyati: {sifir_fiyati}, Outlet Fiyati: {outlet_fiyati}")
                    
                    # Veritabanına kaydet
                    kayit_basarili = urun_kaydet(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati)
                    
                    # Eğer %25 veya daha fazla indirim varsa ve kayıt başarılıysa bildirim gönder
                    if indirim_orani >= 25 and kayit_basarili:
                        # Veritabanında daha önce bildirilip bildirilmediğini kontrol et
                        cursor = conn.cursor()
                        cursor.execute("SELECT bildirildi FROM teknosa_urunler WHERE urun_id = ?", (urun_id,))
                        result = cursor.fetchone()
                        
                        # Eğer bildirildi=0 ise bildirim gönder
                        if result and result[0] == 0:
                            bildirim_basarili = telegram_bildirim_gonder(urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati)
                            if bildirim_basarili:
                                indirim_urun_sayisi += 1
                                # Bildirimi kaydettik olarak işaretle
                                bildirim_durumu_guncelle(conn, urun_id)
                                logger.info(f"Urun {urun_id} icin bildirim gonderildi ve bildirildi=1 olarak isaretlendi.")
                    
                    urun_sayisi += 1
                    
                except Exception as e:
                    logger.error(f"Urun islenirken hata olustu: {str(e)}")
                    continue
            
            # Sonraki sayfaya geçmeyi dene
            try:
                sayfa_no += 1
                # Teknosa'da sayfalar ?pg=2 şeklinde çalışıyor
                sonraki_sayfa_url = url + f"&pg={sayfa_no}"
                logger.info(f"Bir sonraki sayfaya geçiliyor: {sonraki_sayfa_url}")
                driver.get(sonraki_sayfa_url)
                time.sleep(3)
                
                # Sayfanın yüklenip yüklenmediğini kontrol et
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".prd-title"))
                    )
                except TimeoutException:
                    logger.warning(f"Sayfa {sayfa_no} yüklenemedi veya ürün bulunamadı. Tarama sonlandırılıyor.")
                    break
                
            except Exception as e:
                logger.error(f"Sayfa {sayfa_no}'e geçilirken hata oluştu: {str(e)}")
                break
        
        logger.info(f"Toplam {urun_sayisi} urun islendi. {indirim_urun_sayisi} urun %25+ indirimli olarak bildirildi.")
    
    except Exception as e:
        logger.error(f"Tarama sirasinda hata olustu: {str(e)}")
    
    finally:
        # Kaynakları temizle
        driver.quit()
        conn.close()

if __name__ == "__main__":
    logger = setup_logging()
    
    try:
        scan_teknosa_outlet()
    except Exception as e:
        logger.error(f"Program calisirken beklenmeyen bir hata olustu: {str(e)}")