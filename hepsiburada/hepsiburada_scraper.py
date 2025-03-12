#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import io
import codecs
import time
import logging
import sqlite3
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

# Ana dizini Python yoluna ekle
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Telegram notifier'ı import et
from telegram_notifier import get_notifier

# Hepsiburada klasör yolunu tanımla
HEPSIBURADA_DIR = os.path.dirname(os.path.abspath(__file__))

# Konfigürasyon dosyasını yükle
config = configparser.ConfigParser()
config_path = os.path.join(HEPSIBURADA_DIR, 'config.ini')

if not os.path.exists(config_path):
    config['DATABASE'] = {'path': 'hepsiburada_products.db'}
    config['LOGGING'] = {'logfile': 'hepsiburada_scraper.log', 'level': 'INFO'}
    config['TELEGRAM'] = {
        'bot_token': 'YOUR_BOT_TOKEN',
        'chat_id': 'YOUR_CHAT_ID'
    }
    config['URLS'] = {
        'hepsiburada': 'https://www.hepsiburada.com/magaza/hepsiburada?tab=allproducts'
    }
    
    with open(config_path, 'w', encoding='utf-8') as configfile:
        config.write(configfile)
else:
    config.read(config_path, encoding='utf-8')

def setup_logging():
    """Log yapılandırmasını ayarlar."""
    try:
        log_file = os.path.join(HEPSIBURADA_DIR, config['LOGGING'].get('logfile', 'hepsiburada_scraper.log'))
        log_level = config['LOGGING'].get('level', 'INFO')
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            filename=log_file,
            filemode='a',
            encoding='utf-8'
        )
        
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
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)

def setup_db():
    """Veritabanı bağlantısını kurar ve gerekli tabloyu oluşturur."""
    db_path = os.path.join(HEPSIBURADA_DIR, config['DATABASE'].get('path', 'hepsiburada_products.db'))
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS hepsiburada_urunler (
        urun_id TEXT PRIMARY KEY,
        urun_adi TEXT,
        urun_linki TEXT,
        indirim_orani REAL,
        sifir_fiyati REAL,
        indirimli_fiyat REAL,
        ilk_gorulme_tarihi TEXT,
        son_gorulme_tarihi TEXT,
        bildirildi INTEGER DEFAULT 0
    )
    ''')
    
    conn.commit()
    return conn

def setup_driver():
    """Selenium WebDriver'ı yapılandırır ve döndürür."""
    options = Options()
    # options.add_argument("--headless=new")  # Headless modu kapat
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--lang=tr-TR")
    options.add_argument("--charset=UTF-8")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    
    # WebDriver Manager'ı daha sağlam hale getir
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        logging.error(f"WebDriver kurulurken hata oluştu: {str(e)}")
        # Alternatif yöntem dene
        try:
            driver = webdriver.Chrome(options=options)
            return driver
        except Exception as e:
            logging.error(f"Alternatif WebDriver kurulumu da başarısız: {str(e)}")
            raise

def clean_price(price_str):
    """Fiyat stringini temizleyip float değere dönüştürür."""
    if not price_str:
        return 0.0
    
    price_str = price_str.replace("TL", "").strip()
    price_str = price_str.replace(".", "")
    price_str = price_str.replace(",", ".")
    
    try:
        return float(price_str)
    except ValueError:
        return 0.0

def telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat):
    """Telegram üzerinden bildirim gönderir."""
    try:
        notifier = get_notifier(os.path.join(PROJECT_ROOT, 'config.ini'))
        
        product_data = {
            'name': urun_adi,
            'url': urun_linki,
            'original_price': sifir_fiyati,
            'discounted_price': indirimli_fiyat,
            'discount_rate': indirim_orani
        }
        
        success = notifier.send_product_notification(product_data, 'hepsiburada')
        
        if success:
            cursor = conn.cursor()
            cursor.execute("UPDATE hepsiburada_urunler SET bildirildi = 1 WHERE urun_id = ?", (urun_id,))
            conn.commit()
            logging.info(f"Ürün {urun_id} için bildirim gönderildi ve bildirildi=1 olarak işaretlendi.")
            return True
            
        return False
        
    except Exception as e:
        logging.error(f"Telegram bildirimi gönderilirken hata oluştu: {str(e)}")
        return False

def urun_kaydet(conn, urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat):
    """Ürün bilgilerini veritabanına kaydeder."""
    try:
        cursor = conn.cursor()
        simdi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("SELECT * FROM hepsiburada_urunler WHERE urun_id = ?", (urun_id,))
        result = cursor.fetchone()
        
        if result:
            cursor.execute("""
            UPDATE hepsiburada_urunler
            SET urun_adi = ?, urun_linki = ?, indirim_orani = ?, sifir_fiyati = ?, 
                indirimli_fiyat = ?, son_gorulme_tarihi = ?
            WHERE urun_id = ?
            """, (urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat, simdi, urun_id))
            logging.info(f"Ürün güncellendi: {urun_adi}")
            yeni_urun = False
        else:
            cursor.execute("""
            INSERT INTO hepsiburada_urunler 
            (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat, 
             ilk_gorulme_tarihi, son_gorulme_tarihi, bildirildi)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat, simdi, simdi))
            logging.info(f"Yeni ürün kaydedildi: {urun_adi}")
            yeni_urun = True
            
        conn.commit()
        return yeni_urun
    except Exception as e:
        logging.error(f"Ürün kaydedilemedi: {urun_adi}, Hata: {str(e)}")
        return False

def scan_hepsiburada():
    """Hepsiburada mağazasını tarar ve ürünleri işler."""
    logger = logging.getLogger(__name__)
    logger.info("Hepsiburada taraması başlatılıyor...")
    
    conn = setup_db()
    
    try:
        driver = setup_driver()
        
        # Sayfa yükleme zaman aşımını artır
        driver.set_page_load_timeout(60)
        
        url = config['URLS']['hepsiburada']
        logger.info(f"URL açılıyor: {url}")
        driver.get(url)
        
        # Sayfanın yüklenmesi için daha fazla zaman ver
        time.sleep(10)
        
        # Sayfanın yüklendiğini kontrol et
        logger.info("Sayfa yüklendi, ürünler aranıyor...")
        
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.productListContent-zAP0Y5msy8OHn5z7T_K_"))
            )
        except TimeoutException:
            logger.error("Ürün listesi bulunamadı. Sayfa yapısı değişmiş olabilir.")
            # Sayfa kaynağını kaydet
            with open("hepsiburada_page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info("Sayfa kaynağı 'hepsiburada_page_source.html' dosyasına kaydedildi.")
            raise
        
        urun_sayisi = 0
        indirim_urun_sayisi = 0
        islenen_urun_idleri = set()
        
        while True:
            urunler = driver.find_elements(By.CSS_SELECTOR, "li.productListContent-zAP0Y5msy8OHn5z7T_K_")
            logger.info(f"Sayfada {len(urunler)} adet ürün bulundu.")
            
            if not urunler:
                break
                
            for urun in urunler:
                try:
                    # Ürün ID'sini al
                    urun_id = urun.get_attribute('id')
                    if not urun_id or urun_id in islenen_urun_idleri:
                        continue
                        
                    islenen_urun_idleri.add(urun_id)
                    
                    # Ürün adını al
                    try:
                        urun_adi = urun.find_element(By.CSS_SELECTOR, 'h3[data-test-id="product-card-name"]').text.strip()
                    except:
                        continue
                    
                    # Ürün linkini al
                    try:
                        urun_linki = urun.find_element(By.CSS_SELECTOR, 'a[data-test-id="product-card-link"]').get_attribute('href')
                    except:
                        continue
                    
                    # Fiyat bilgilerini al
                    try:
                        fiyat_element = urun.find_element(By.CSS_SELECTOR, 'div[data-test-id="price-current-price"]')
                        indirimli_fiyat = clean_price(fiyat_element.text)
                        
                        sifir_fiyat_element = urun.find_element(By.CSS_SELECTOR, 'div[data-test-id="price-prev-price"]')
                        sifir_fiyati = clean_price(sifir_fiyat_element.text)
                        
                        if sifir_fiyati > 0 and indirimli_fiyat > 0:
                            indirim_orani = ((sifir_fiyati - indirimli_fiyat) / sifir_fiyati) * 100
                        else:
                            indirim_orani = 0
                            
                    except:
                        continue
                    
                    logger.info(f"Ürün: {urun_adi}, İndirim: %{indirim_orani:.2f}, "
                              f"Sıfır Fiyatı: {sifir_fiyati}, İndirimli Fiyat: {indirimli_fiyat}")
                    
                    # Veritabanına kaydet
                    kayit_basarili = urun_kaydet(conn, urun_id, urun_adi, urun_linki, 
                                               indirim_orani, sifir_fiyati, indirimli_fiyat)
                    
                    # İndirim oranı %25'ten fazlaysa bildirim gönder
                    if indirim_orani >= 25:
                        cursor = conn.cursor()
                        cursor.execute("SELECT bildirildi FROM hepsiburada_urunler WHERE urun_id = ?", (urun_id,))
                        result = cursor.fetchone()
                        
                        if result and result[0] == 0:
                            telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki,
                                                   indirim_orani, sifir_fiyati, indirimli_fiyat)
                            indirim_urun_sayisi += 1
                    
                    urun_sayisi += 1
                    
                except Exception as e:
                    logger.error(f"Ürün işlenirken hata oluştu: {str(e)}")
                    continue
            
            # Daha fazla ürün yükle
            try:
                load_more = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.moria-LoadMore-button"))
                )
                driver.execute_script("arguments[0].click();", load_more)
                time.sleep(3)
            except:
                logger.info("Daha fazla ürün bulunamadı.")
                break
        
        logger.info(f"Toplam {urun_sayisi} ürün işlendi. {indirim_urun_sayisi} ürün %25+ indirimli olarak bildirildi.")
        
    except Exception as e:
        logger.error(f"Tarama sırasında hata oluştu: {str(e)}")
        # Hata durumunda sayfa kaynağını kaydet
        try:
            with open("hepsiburada_error_page.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info("Hata sayfası 'hepsiburada_error_page.html' dosyasına kaydedildi.")
        except:
            logger.error("Hata sayfası kaydedilemedi.")
    
    finally:
        try:
            driver.quit()
        except:
            pass
        conn.close()

if __name__ == "__main__":
    logger = setup_logging()
    scan_hepsiburada() 