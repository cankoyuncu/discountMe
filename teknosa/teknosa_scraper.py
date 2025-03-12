#!/usr/bin/env python
# -*- coding: utf-8 -*-

# İlk olarak temel modüller import edilir
import os
import sys

# Ana dizini Python yoluna ekle
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import io
import codecs
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

# Telegram notifier'ı import et
from telegram_notifier import get_notifier

# sys.stdout için UTF-8 encoding sağla (Windows konsol çıktılarında Türkçe karakterler için)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Teknosa klasör yolunu tanımla - normalizasyon ekleniyor
TEKNOSA_DIR = os.path.dirname(os.path.abspath(__file__))

# Konfigürasyon dosyasını yükle - normalize edilmiş yollar kullan
config = configparser.ConfigParser(interpolation=None)
config_path = os.path.normpath(os.path.join(TEKNOSA_DIR, 'config.ini'))
if not os.path.exists(config_path):
    # Eğer config dosyası yoksa, örnek bir config oluştur
    config['DATABASE'] = {'path': os.path.join(TEKNOSA_DIR, 'teknosa_products.db')}
    config['LOGGING'] = {'logfile': os.path.join(TEKNOSA_DIR, 'teknosa_scraper.log'), 'level': 'INFO'}
    config['TELEGRAM'] = {'bottoken': 'YOUR_BOT_TOKEN', 'chatid': 'YOUR_CHAT_ID'}
    config['URLS'] = {
        'teknosaoutlet': 'https://www.teknosa.com/outlet?sort=newProduct-desc&s=%3AbestSellerPoint-desc'
    }
    
    with open(config_path, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
else:
    # UTF-8 encoding ile config dosyasını oku
    try:
        config.read(config_path, encoding='utf-8')
    except:
        # Eğer UTF-8 ile okuma başarısız olursa başka encoding'ler dene
        config.read(config_path, encoding='latin-1')

def setup_logging():
    """Log yapılandırmasını ayarlar."""
    # Make sure we're using the correct directory
    try:
        log_file = os.path.join(TEKNOSA_DIR, config['LOGGING'].get('logfile', 'teknosa_scraper.log'))
        log_level = config['LOGGING'].get('level', 'INFO')
        
        # Log dosya yolu için normalizasyon ekleyerek Windows'ta path sorunlarını önle
        log_file_path = os.path.normpath(os.path.abspath(log_file))
        
        # Ensure the directory exists - Eğer log dosyasının klasörü yoksa oluştur
        log_dir = os.path.dirname(log_file_path)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # Debug için log dosyası yolunu yazdır
        print(f"Log dosyası yolu: {log_file_path}")
        
        # Logging konfigürasyonu
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            filename=log_file_path,
            filemode='a',
            encoding='utf-8'  # UTF-8 karakter kodlaması
        )
        
        # Konsol çıktısı için handler ekle
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(getattr(logging, log_level))
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console.setFormatter(formatter)
        logging.getLogger('').addHandler(console)
        
        logger = logging.getLogger(__name__)
        logger.info("Loglama başlatıldı")
        return logger
        
    except Exception as e:
        print(f"Log ayarları yapılandırılırken hata oluştu: {str(e)}")
        # En azından basit bir logger oluştur
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        return logging.getLogger(__name__)

def setup_db():
    """Veritabani baglantisini kurar ve gerekli tabloyu olusturur."""
    db_path = os.path.join(TEKNOSA_DIR, config['DATABASE'].get('path', 'teknosa_products.db'))
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Urunler tablosunu olustur
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teknosa_urunler (
        urun_id TEXT PRIMARY KEY,
        urun_adi TEXT,
        urun_linki TEXT,
        indirim_orani REAL,
        sifir_fiyati REAL,
        outlet_fiyati REAL,
        ilk_gorulme_tarihi TEXT,
        son_gorulme_tarihi TEXT,
        bildirildi INTEGER DEFAULT 0
    )
    ''')
    
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
    # Karakter kodlaması için gerekli parametreler
    options.add_argument("--lang=tr-TR") 
    options.add_argument("--charset=UTF-8")

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
        return 0.0

def telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati):
    """Telegram üzerinden bildirim gönderir."""
    try:
        # Telegram notifier'ı al
        notifier = get_notifier(os.path.join(TEKNOSA_DIR, 'config.ini'))
        
        # Ürün verilerini hazırla
        product_data = {
            'name': urun_adi,
            'url': urun_linki,
            'original_price': sifir_fiyati,
            'discounted_price': outlet_fiyati,
            'discount_rate': indirim_orani
        }
        
        # Bildirimi gönder
        success = notifier.send_product_notification(product_data, 'teknosa')
        
        if success:
            # Bildirim durumunu güncelle
            cursor = conn.cursor()
            cursor.execute("UPDATE teknosa_urunler SET bildirildi = 1 WHERE urun_id = ?", (urun_id,))
            conn.commit()
            logging.info(f"Urun {urun_id} icin bildirim gonderildi ve bildirildi=1 olarak isaretlendi.")
            return True
            
        return False
        
    except Exception as e:
        logging.error(f"Telegram bildirimi gönderilirken hata oluştu: {str(e)}")
        return False

def urun_kaydet(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati):
    """Ürün bilgilerini veritabanına kaydeder."""
    try:
        cursor = conn.cursor()
        simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Ürün veritabanında var mı kontrol et
        cursor.execute("SELECT * FROM teknosa_urunler WHERE urun_id = ?", (urun_id,))
        result = cursor.fetchone()
        
        if result:
            # Ürün güncelle
            cursor.execute("""
            UPDATE teknosa_urunler
            SET urun_adi = ?, urun_linki = ?, indirim_orani = ?, sifir_fiyati = ?, outlet_fiyati = ?, son_gorulme_tarihi = ?
            WHERE urun_id = ?
            """, (urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati, simdi, urun_id))
            logging.info(f"Urun guncellendi: {urun_adi}")
            yeni_urun = False
        else:
            # Yeni ürün ekle
            cursor.execute("""
            INSERT INTO teknosa_urunler (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati, ilk_gorulme_tarihi, son_gorulme_tarihi, bildirildi)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati, simdi, simdi))
            logging.info(f"Yeni urun kaydedildi: {urun_adi}")
            yeni_urun = True
            
        conn.commit()
        return yeni_urun
    except Exception as e:
        logging.error(f"Urun kaydedilemedi: {urun_adi}, Hata: {str(e)}")
        return False

# Log mesajlarını Türkçe karakter desteği ile güncelleyelim
def log_safe(logger, level, message):
    """Türkçe karakterleri güvenli şekilde loglar."""
    try:
        # Mesajı Unicode olarak ele al
        if isinstance(message, bytes):
            message = message.decode('utf-8')
            
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "debug":
            logger.debug(message)
    except UnicodeEncodeError:
        # Eğer Türkçe karakter sorunu olursa ASCII ile deneyin
        ascii_message = message.encode('ascii', 'replace').decode('ascii')
        if level == "info":
            logger.info(ascii_message)
        elif level == "warning":
            logger.warning(ascii_message)
        elif level == "error":
            logger.error(ascii_message)
        elif level == "debug":
            logger.debug(ascii_message)

def scan_teknosa_outlet():
    """Teknosa outlet sayfasini tarar ve urunleri isler."""
    logger = logging.getLogger(__name__)
    logger.info("Teknosa outlet taramasi baslatiliyor...")
    
    conn = setup_db()
    driver = setup_driver()
    
    try:
        # Teknosa outlet URL'sini yükle
        url = config['URLS']['teknosaoutlet']
        driver.get(url)
        time.sleep(5)  # Sayfanın yüklenmesini bekle
        
        # Sayfa yüklenmesini bekle
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".prd-title"))
        )
        
        urun_sayisi = 0
        indirim_urun_sayisi = 0
        max_sayfa = 10  # Maksimum taranacak sayfa sayısı
        islenen_urun_idleri = set()  # İşlenen ürün ID'lerini takip et
        
        sayfa_no = 1
        
        while sayfa_no <= max_sayfa:
            logger.info(f"Sayfa {sayfa_no} taraniyor...")
            
            # Sayfadaki tüm ürün elementlerini bul
            urunler = driver.find_elements(By.CSS_SELECTOR, ".prd")
            logger.info(f"Sayfa {sayfa_no}'de {len(urunler)} adet ürün bulundu.")
            
            if not urunler:
                logger.warning(f"Sayfa {sayfa_no}'de ürün bulunamadı. Tarama sonlandırılıyor.")
                break
            
            # Mevcut ürün sayısını kaydet - daha sonra yeni ürünlerin gelip gelmediğini kontrol etmek için
            mevcut_urun_sayisi = len(urunler)
            
            # Her ürünü işle
            for urun in urunler:
                try:
                    # Ürün ID'sini al
                    try:
                        urun_id = urun.get_attribute('data-product-id')
                        if not urun_id:
                            logger.warning("Ürün ID'si bulunamadı, bu ürün atlanıyor.")
                            continue
                        
                        # Bu ID daha önce işlendiyse atla
                        if urun_id in islenen_urun_idleri:
                            logger.debug(f"Ürün ID: {urun_id} daha önce işlendi, atlanıyor.")
                            continue
                        
                        islenen_urun_idleri.add(urun_id)
                        logger.info(f"Islenen urun ID: {urun_id}")
                    except (NoSuchElementException, ValueError) as e:
                        logger.warning(f"Ürün ID alınırken hata: {str(e)}")
                        continue
                    
                    # Ürün adını al - teknosa-prd.md'ye göre h3.prd-title içinde
                    try:
                        urun_adi_element = urun.find_element(By.CSS_SELECTOR, "h3.prd-title")
                        urun_adi = urun_adi_element.text.strip()
                        if not urun_adi:
                            urun_adi = "Bilinmeyen Ürün"
                    except NoSuchElementException:
                        urun_adi = "Bilinmeyen Ürün"
                        logger.warning(f"Ürün {urun_id} için ad bulunamadı.")
                    
                    # Ürün linkini al - teknosa-prd.md'ye göre a.prd-link içinde
                    try:
                        urun_linki = urun.find_element(By.CSS_SELECTOR, "a.prd-link").get_attribute("href")
                    except NoSuchElementException:
                        urun_linki = f"https://www.teknosa.com/outlet/{urun_id}"
                        logger.warning(f"Ürün {urun_id} için link bulunamadı.")
                    
                    # İndirim oranını al - teknosa-prd.md'ye göre div.prd-discount içinde
                    try:
                        indirim_elementi = urun.find_element(By.CSS_SELECTOR, "div.prd-discount")
                        indirim_text = indirim_elementi.text.strip().replace("%", "").replace("-", "")
                        indirim_orani = float(indirim_text)
                    except (NoSuchElementException, ValueError):
                        # Eğer indirim oranı yoksa veya okunamazsa, data-discount özniteliğine bakılır
                        try:
                            indirim_orani = float(urun.get_attribute('data-product-discount-rate') or 0)
                        except (ValueError, TypeError):
                            indirim_orani = 0
                            logger.warning(f"Ürün {urun_id} için indirim oranı hesaplanamadı.")
                    
                    # Sıfır fiyatını al - teknosa-prd.md'ye göre div.prd-prc1 span.prc-first içinde
                    try:
                        sifir_fiyati_element = urun.find_element(By.CSS_SELECTOR, "div.prd-prc1 span.prc-first")
                        sifir_fiyati_text = sifir_fiyati_element.text.strip()
                        sifir_fiyati = clean_price(sifir_fiyati_text)
                    except (NoSuchElementException, ValueError):
                        try:
                            sifir_fiyati = float(urun.get_attribute('data-product-actual-price') or 0)
                        except (ValueError, TypeError):
                            sifir_fiyati = 0
                            logger.warning(f"Ürün {urun_id} için sıfır fiyatı hesaplanamadı.")
                    
                    # Outlet fiyatını al - teknosa-prd.md'ye göre div.prd-prc2 span.prc-last içinde
                    try:
                        outlet_fiyati_element = urun.find_element(By.CSS_SELECTOR, "div.prd-prc2 span.prc-last")
                        outlet_fiyati_text = outlet_fiyati_element.text.strip()
                        outlet_fiyati = clean_price(outlet_fiyati_text)
                    except (NoSuchElementException, ValueError):
                        try:
                            outlet_fiyati = float(urun.get_attribute('data-product-discounted-price') or 0)
                        except (ValueError, TypeError):
                            outlet_fiyati = 0
                            logger.warning(f"Ürün {urun_id} için outlet fiyatı hesaplanamadı.")
                    
                    logger.info(f"Urun: {urun_adi}, Indirim: %{indirim_orani}, Sifir Fiyati: {sifir_fiyati}, Outlet Fiyati: {outlet_fiyati}")
                    
                    # Veritabanına kaydet
                    kayit_basarili = urun_kaydet(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati)
                    
                    # Eğer %25 veya daha fazla indirim varsa ve kayıt başarılıysa bildirim gönder
                    if indirim_orani >= 25:
                        # Veritabanında daha önce bildirilip bildirilmediğini kontrol et
                        cursor = conn.cursor()
                        cursor.execute("SELECT bildirildi FROM teknosa_urunler WHERE urun_id = ?", (urun_id,))
                        result = cursor.fetchone()
                        
                        # Eğer bildirildi=0 ise veya yeni kayıtsa bildirim gönder
                        if result and result[0] == 0:
                            # HTML formatında bildirim mesajı oluştur
                            bildirim_mesaji = f"""
🔥 <b>OUTLET FIRSATI!</b> 🔥
✅ {urun_adi}

💰 <b>Outlet Fiyatı:</b> {outlet_fiyati:.2f} TL
📌 <b>Sıfır Fiyatı:</b> {sifir_fiyati:.2f} TL
🏷️ <b>Indirim:</b> %{indirim_orani} ({sifir_fiyati - outlet_fiyati:.2f} TL)

🔗 <a href="{urun_linki}">Satin almak icin tiklayin</a>
"""
                            telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, outlet_fiyati)
                            indirim_urun_sayisi += 1
                    
                    urun_sayisi += 1
                    
                except Exception as e:
                    logger.error(f"Urun islenirken hata olustu: {str(e)}")
                    continue
            
            sayfa_no += 1
            
            # "Daha Fazla Ürün Gör" butonuna tıklamayı dene
            # teknosa-prd.md dosyasındaki button.btn.btn-extra.plp-paging-load-more seçicisine göre
            try:
                # Sayfanın sonuna kaydır - daha fazla ürün göster butonu sayfanın sonundadır
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # Scroll işlemi için bekle
                
                # Teknosa-prd.md dosyasında belirtilen tam CSS seçiciyi kullan
                daha_fazla_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.btn-extra.plp-paging-load-more"))
                )
                
                # Butonun görünür olduğundan emin ol ve sayfayı kaydır
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", daha_fazla_button)
                time.sleep(1)  # Sayfanın kaydırılmasını bekle
                
                # Buton metnini UTF-8 ile dekode ederek logla
                try:
                    buton_metni = daha_fazla_button.text
                    logger.info(f"Bulunan buton metni: {buton_metni}")
                except:
                    logger.info("Butonun metni alınamadı.")
                
                # Butona tıkla
                driver.execute_script("arguments[0].click();", daha_fazla_button)
                logger.info(f"'Daha Fazla Ürün Gör' butonuna tıklandı. Sayfa {sayfa_no} yükleniyor...")
                
                # Yeni ürünlerin yüklenmesi için biraz daha uzun bekle
                time.sleep(5) 
                
                # Yeni ürünlerin geldiğinden emin ol - 10 saniye bekleyerek kontrol et
                try:
                    WebDriverWait(driver, 10).until(
                        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".prd")) > mevcut_urun_sayisi
                    )
                    log_safe(logger, "info", f"Yeni ürünler yüklendi. Önceki: {mevcut_urun_sayisi}, Şimdi: {len(driver.find_elements(By.CSS_SELECTOR, '.prd'))}")
                except TimeoutException:
                    log_safe(logger, "warning", "Yeni ürünler yüklenmedi veya yeni ürün yok. Tarama sonlandırılıyor.")
                    break
                    
            except TimeoutException:
                log_safe(logger, "info", "'Daha Fazla Ürün Gör' butonu bulunamadı. Muhtemelen son sayfadayız.")
                break
                
            except Exception as e:
                log_safe(logger, "info", f"'Daha Fazla Ürün Gör' işlemi sırasında hata: {str(e)}")
                log_safe(logger, "info", "Tarama tamamlandı.")
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
    scan_teknosa_outlet()