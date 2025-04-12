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
        'hepsiburada': 'https://www.hepsiburada.com/magaza/hepsiburada?siralama=enyeni&tab=allproducts'
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
    
    logging.info(f"Ham fiyat string: '{price_str}'")
    
    # TL, ₺ ve boşlukları temizle
    price_str = price_str.replace("TL", "").replace("₺", "").strip()
    
    # Noktalama ve binlik ayraçlarını temizle
    price_str = price_str.replace(".", "")  # Binlik ayracı
    price_str = price_str.replace(",", ".")  # Ondalık ayracı
    
    logging.info(f"Temizlenmiş fiyat string: '{price_str}'")
    
    try:
        return float(price_str)
    except ValueError as e:
        logging.error(f"Fiyat dönüştürme hatası: {str(e)}, String: '{price_str}'")
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
        
        # Debug bilgisi
        logging.info(f"Veritabanına kaydediliyor: ID={urun_id}, Ad={urun_adi}, İndirim=%{indirim_orani:.2f}")
        
        cursor.execute("SELECT * FROM hepsiburada_urunler WHERE urun_id = ?", (urun_id,))
        result = cursor.fetchone()
        
        if result:
            # Ürün zaten var, güncelleme yap
            cursor.execute("""
            UPDATE hepsiburada_urunler
            SET urun_adi = ?, urun_linki = ?, indirim_orani = ?, sifir_fiyati = ?, 
                indirimli_fiyat = ?, son_gorulme_tarihi = ?
            WHERE urun_id = ?
            """, (urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat, simdi, urun_id))
            logging.info(f"Ürün güncellendi: {urun_adi}")
            yeni_urun = False
        else:
            # Yeni ürün ekle
            cursor.execute("""
            INSERT INTO hepsiburada_urunler 
            (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat, 
             ilk_gorulme_tarihi, son_gorulme_tarihi, bildirildi)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (urun_id, urun_adi, urun_linki, indirim_orani, sifir_fiyati, indirimli_fiyat, simdi, simdi))
            logging.info(f"Yeni ürün eklendi: {urun_adi}")
            yeni_urun = True
            
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Ürün kaydedilirken hata oluştu: {urun_adi}, Hata: {str(e)}")
        return False

def scan_hepsiburada():
    """Hepsiburada mağazasını tarar ve ürünleri işler."""
    logger = logging.getLogger(__name__)
    logger.info("Hepsiburada taraması başlatılıyor...")
    
    conn = setup_db()
    driver = None
    
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
        
        # Önce eski CSS seçiciyi deneyelim
        urunler = driver.find_elements(By.CSS_SELECTOR, "li.productListContent-zAP0Y5msy8OHn5z7T_K_")
        
        # Eğer eski seçici çalışmazsa, yeni seçiciyi deneyelim
        if not urunler or len(urunler) == 0:
            logger.info("Eski CSS seçici çalışmadı, yeni seçiciyi deniyorum...")
            urunler = driver.find_elements(By.CSS_SELECTOR, "a.productCardLink-XUJYBO4aGZl6zvMNIzAJ")
            
            # Bu da çalışmazsa tüm ürün kartlarını bulalım
            if not urunler or len(urunler) == 0:
                logger.info("Yeni seçici de çalışmadı, tüm ürün kartlarını deniyorum...")
                urunler = driver.find_elements(By.CSS_SELECTOR, "div.productCard-GfFnhVSbQq53u9Ag6N4e")
        
        logger.info(f"Sayfada {len(urunler)} adet ürün bulundu.")
        
        # Sayfa kaynağını kaydet (hata ayıklama için)
        with open(os.path.join(HEPSIBURADA_DIR, "hepsiburada_page_source.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Sayfa kaynağı 'hepsiburada_page_source.html' dosyasına kaydedildi.")
        
        if not urunler or len(urunler) == 0:
            logger.error("Hiç ürün bulunamadı. Sayfa yapısı değişmiş olabilir.")
            return
        
        urun_sayisi = 0
        indirim_urun_sayisi = 0
        islenen_urun_idleri = set()
        
        # İlk ürünü debug için detaylı inceleyelim
        if urunler and len(urunler) > 0:
            first_product = urunler[0]
            logger.info(f"İlk ürün HTML: {first_product.get_attribute('outerHTML')}")
        
        for urun_index, urun in enumerate(urunler):
            try:
                logger.info(f"Ürün {urun_index+1}/{len(urunler)} işleniyor...")
                
                # HTML yapısına göre uygun ürün ID'si belirle
                try:
                    urun_id = urun.get_attribute('id')
                    if not urun_id or urun_id.strip() == "":
                        # Eğer ID yoksa, ürün linkindeki ürün kodunu kullan
                        try:
                            urun_linki = urun.get_attribute('href') or ""
                            if "p-" in urun_linki:
                                urun_id = urun_linki.split("p-")[1].split("?")[0]
                            else:
                                urun_id = f"urun_{urun_index}"
                        except:
                            urun_id = f"urun_{urun_index}"
                except:
                    urun_id = f"urun_{urun_index}"
                
                logger.info(f"Ürün ID: {urun_id}")
                
                if urun_id in islenen_urun_idleri:
                    logger.info(f"Ürün ID {urun_id} daha önce işlenmiş, atlanıyor.")
                    continue
                
                islenen_urun_idleri.add(urun_id)
                
                # Ürün linkini al (hem doğrudan hem de içindeki a etiketinden)
                try:
                    urun_linki = urun.get_attribute('href')
                    if not urun_linki:
                        try:
                            link_element = urun.find_element(By.TAG_NAME, 'a')
                            urun_linki = link_element.get_attribute('href')
                        except:
                            # Parent üzerinden link bulmayı deneyelim
                            try:
                                parent = urun.find_element(By.XPATH, '..')
                                urun_linki = parent.get_attribute('href')
                            except:
                                urun_linki = f"https://www.hepsiburada.com/magaza/hepsiburada?urun={urun_id}"
                    
                    logger.info(f"Ürün linki: {urun_linki}")
                except Exception as e:
                    logger.error(f"Ürün linki alınamadı: {str(e)}")
                    urun_linki = f"https://www.hepsiburada.com/magaza/hepsiburada?urun={urun_id}"
                
                # Ürün adını al - çeşitli seçiciler dene
                try:
                    # Birden fazla seçiciyi sırayla dene
                    selectors = [
                        'h3[data-test-id="product-card-name"]',
                        'span.title-qp6D86wJ1SVIfbfer5xg',
                        'h2.title-wupXHSGzcP0QBsfFSpmz',
                        'h3.moria-ProductCard-aBQpD',
                        'h2[data-test-id="title-1"]'
                    ]
                    
                    urun_adi = None
                    for selector in selectors:
                        try:
                            element = urun.find_element(By.CSS_SELECTOR, selector)
                            urun_adi = element.text.strip()
                            if urun_adi:
                                logger.info(f"Ürün adı bulundu ({selector}): {urun_adi}")
                                break
                        except:
                            continue
                    
                    # Hiçbir seçici çalışmadıysa, alternatif yöntem dene
                    if not urun_adi:
                        # title veya alt attribute dene
                        urun_adi = urun.get_attribute('title') or urun.get_attribute('alt') or f"Ürün {urun_id}"
                        logger.info(f"Alternatif ürün adı: {urun_adi}")
                
                except Exception as e:
                    logger.error(f"Ürün adı alınamadı: {str(e)}")
                    urun_adi = f"Ürün {urun_id}"
                
                # Fiyat bilgilerini al - çeşitli seçiciler dene
                indirimli_fiyat = 0
                sifir_fiyati = 0
                indirim_orani = 0
                
                try:
                    # İndirimli fiyat için çeşitli seçiciler
                    indirimli_fiyat_selectors = [
                        'div[data-test-id="price-current-price"]',
                        'div[data-test-id="final-price-1"]',
                        'div.price-R57b2z0LFOTTCaDIKTgo',
                        'div.sfqpphpe1vz'
                    ]
                    
                    indirimli_fiyat_text = None
                    for selector in indirimli_fiyat_selectors:
                        try:
                            element = urun.find_element(By.CSS_SELECTOR, selector)
                            indirimli_fiyat_text = element.text
                            if indirimli_fiyat_text:
                                logger.info(f"İndirimli fiyat bulundu ({selector}): {indirimli_fiyat_text}")
                                break
                        except:
                            continue
                    
                    if indirimli_fiyat_text:
                        indirimli_fiyat = clean_price(indirimli_fiyat_text)
                        logger.info(f"Temizlenmiş indirimli fiyat: {indirimli_fiyat}")
                    else:
                        logger.error("İndirimli fiyat bulunamadı")
                        continue  # Fiyat bulunamazsa ürünü atla
                    
                    # Normal fiyat için çeşitli seçiciler
                    normal_fiyat_selectors = [
                        'div[data-test-id="price-prev-price"]',
                        'div.previous-price',
                        's.oldPrice'
                    ]
                    
                    normal_fiyat_text = None
                    for selector in normal_fiyat_selectors:
                        try:
                            elements = urun.find_elements(By.CSS_SELECTOR, selector)
                            if elements and len(elements) > 0:
                                normal_fiyat_text = elements[0].text
                                if normal_fiyat_text:
                                    logger.info(f"Normal fiyat bulundu ({selector}): {normal_fiyat_text}")
                                    break
                        except:
                            continue
                    
                    if normal_fiyat_text:
                        sifir_fiyati = clean_price(normal_fiyat_text)
                        logger.info(f"Temizlenmiş normal fiyat: {sifir_fiyati}")
                        
                        # İndirim oranını hesapla
                        if sifir_fiyati > 0 and indirimli_fiyat > 0 and sifir_fiyati > indirimli_fiyat:
                            indirim_orani = ((sifir_fiyati - indirimli_fiyat) / sifir_fiyati) * 100
                            logger.info(f"Hesaplanan indirim oranı: %{indirim_orani:.2f}")
                        else:
                            logger.info("Geçerli bir indirim bulunamadı.")
                            indirim_orani = 0
                    else:
                        logger.info("Normal fiyat bulunamadı, indirim yok.")
                        sifir_fiyati = indirimli_fiyat
                        indirim_orani = 0
                    
                except Exception as e:
                    logger.error(f"Fiyat bilgileri alınırken hata: {str(e)}")
                    continue
                
                # TÜM ÜRÜNLERİ KAYDET - indirim olmasa bile
                logger.info(f"Ürün: {urun_adi}, Fiyat: {indirimli_fiyat} TL, İndirim: %{indirim_orani:.2f}")
                
                # Veritabanına kaydet
                try:
                    kayit_basarili = urun_kaydet(conn, urun_id, urun_adi, urun_linki, 
                                            indirim_orani, sifir_fiyati, indirimli_fiyat)
                    if kayit_basarili:
                        logger.info(f"Ürün veritabanına kaydedildi: {urun_adi}")
                        urun_sayisi += 1
                    else:
                        logger.error(f"Ürün kaydedilemedi: {urun_adi}")
                    
                    # İndirim oranı %5'ten fazlaysa bildirim gönder
                    if indirim_orani >= 5:
                        cursor = conn.cursor()
                        cursor.execute("SELECT bildirildi FROM hepsiburada_urunler WHERE urun_id = ?", (urun_id,))
                        result = cursor.fetchone()
                        
                        if result and result[0] == 0:
                            bildirim_basarili = telegram_bildirim_gonder(conn, urun_id, urun_adi, urun_linki,
                                                  indirim_orani, sifir_fiyati, indirimli_fiyat)
                            if bildirim_basarili:
                                indirim_urun_sayisi += 1
                                logger.info(f"Telegram bildirimi gönderildi: {urun_adi}")
                            else:
                                logger.error(f"Telegram bildirimi gönderilemedi: {urun_adi}")
                    
                except Exception as e:
                    logger.error(f"Ürün kaydedilirken hata: {str(e)}")
                    continue
                
            except Exception as e:
                logger.error(f"Ürün işlenirken hata: {str(e)}")
                continue
        
        # Daha fazla ürün yükleme kodu buraya...
        
        logger.info(f"Toplam {urun_sayisi} ürün işlendi. {indirim_urun_sayisi} ürün %5+ indirimli olarak bildirildi.")
        
    except Exception as e:
        logger.error(f"Tarama sırasında hata: {str(e)}")
        if driver:
            try:
                with open(os.path.join(HEPSIBURADA_DIR, "hepsiburada_error_page.html"), "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info("Hata sayfası 'hepsiburada_error_page.html' dosyasına kaydedildi.")
            except:
                pass
    
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        conn.close()

if __name__ == "__main__":
    logger = setup_logging()
    scan_hepsiburada() 