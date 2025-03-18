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
        
        # Eğer eski seçici çalışmazsa, yeni seçiciyi deneyelim (hepsiburada-prd.md'deki son örneğe göre)
        if not urunler:
            logger.info("Eski CSS seçici çalışmadı, yeni seçiciyi deniyorum...")
            urunler = driver.find_elements(By.CSS_SELECTOR, "a.productCardLink-XUJYBO4aGZl6zvMNIzAJ")
        
        logger.info(f"Sayfada {len(urunler)} adet ürün bulundu.")
        
        # Sayfa kaynağını kaydet (hata ayıklama için)
        with open(os.path.join(HEPSIBURADA_DIR, "hepsiburada_page_source.html"), "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        logger.info("Sayfa kaynağı 'hepsiburada_page_source.html' dosyasına kaydedildi.")
        
        if not urunler:
            logger.error("Hiç ürün bulunamadı. Sayfa yapısı değişmiş olabilir.")
            return
        
        urun_sayisi = 0
        indirim_urun_sayisi = 0
        islenen_urun_idleri = set()
        
        for urun_index, urun in enumerate(urunler):
            try:
                logger.info(f"Ürün {urun_index+1} işleniyor...")
                
                # Her ürün için HTML'i incele
                urun_html = urun.get_attribute('outerHTML')
                logger.info(f"Ürün HTML (ilk 200 karakter): {urun_html[:200]}...")
                
                # Ürün ID'sini belirle (yeni yapıda ürün ID'si olmayabilir, bu durumda index kullanıyoruz)
                urun_id = urun.get_attribute('id') or f"urun_{urun_index}"
                
                if urun_id in islenen_urun_idleri:
                    logger.info(f"Ürün ID {urun_id} daha önce işlenmiş, atlanıyor.")
                    continue
                
                islenen_urun_idleri.add(urun_id)
                
                # Yeni HTML yapısı için ürün linkini al
                try:
                    urun_linki = urun.get_attribute('href')
                    if not urun_linki:
                        # Eğer direkt link yoksa, içindeki a etiketini bul
                        link_element = urun.find_element(By.TAG_NAME, 'a')
                        urun_linki = link_element.get_attribute('href')
                    logger.info(f"Ürün linki: {urun_linki}")
                except Exception as e:
                    logger.error(f"Ürün linki alınamadı: {str(e)}")
                    continue
                
                # Ürün adını al - eski ve yeni HTML yapısını dene
                try:
                    # Önce eski yapıyı dene
                    try:
                        urun_adi_element = urun.find_element(By.CSS_SELECTOR, 'h3[data-test-id="product-card-name"]')
                        urun_adi = urun_adi_element.text.strip()
                    except:
                        # Sonra yeni yapıyı dene
                        try:
                            urun_adi_element = urun.find_element(By.CSS_SELECTOR, 'span.title-qp6D86wJ1SVIfbfer5xg')
                            urun_adi = urun_adi_element.text.strip()
                        except:
                            # Başka bir seçici dene
                            urun_adi_element = urun.find_element(By.CSS_SELECTOR, 'h2.title-wupXHSGzcP0QBsfFSpmz')
                            urun_adi = urun_adi_element.text.strip()
                    
                    logger.info(f"Ürün adı: {urun_adi}")
                except Exception as e:
                    logger.error(f"Ürün adı alınamadı: {str(e)}")
                    continue
                
                # Fiyat bilgilerini al - eski ve yeni HTML yapısını dene
                try:
                    # İndirimli fiyat - eski seçiciyi dene
                    try:
                        indirimli_fiyat_element = urun.find_element(By.CSS_SELECTOR, 'div[data-test-id="price-current-price"]')
                        indirimli_fiyat_text = indirimli_fiyat_element.text
                    except:
                        # Yeni seçiciyi dene
                        try:
                            indirimli_fiyat_element = urun.find_element(By.CSS_SELECTOR, 'div[data-test-id="final-price-1"]')
                            indirimli_fiyat_text = indirimli_fiyat_element.text
                        except:
                            # Başka bir seçici dene
                            indirimli_fiyat_element = urun.find_element(By.CSS_SELECTOR, 'div.price-R57b2z0LFOTTCaDIKTgo')
                            indirimli_fiyat_text = indirimli_fiyat_element.text
                    
                    logger.info(f"İndirimli fiyat (ham): {indirimli_fiyat_text}")
                    indirimli_fiyat = clean_price(indirimli_fiyat_text)
                    logger.info(f"İndirimli fiyat (temiz): {indirimli_fiyat}")
                    
                    # Normal fiyat - önce eski seçiciyi dene
                    try:
                        normal_fiyat_element = urun.find_element(By.CSS_SELECTOR, 'div[data-test-id="price-prev-price"]')
                        normal_fiyat_text = normal_fiyat_element.text
                        logger.info(f"Normal fiyat (ham): {normal_fiyat_text}")
                        sifir_fiyati = clean_price(normal_fiyat_text)
                        logger.info(f"Normal fiyat (temiz): {sifir_fiyati}")
                        
                        # İndirim oranını hesapla
                        if sifir_fiyati > 0 and indirimli_fiyat > 0 and sifir_fiyati > indirimli_fiyat:
                            indirim_orani = ((sifir_fiyati - indirimli_fiyat) / sifir_fiyati) * 100
                            logger.info(f"İndirim oranı: %{indirim_orani:.2f}")
                        else:
                            logger.info("Geçerli bir indirim bulunamadı.")
                            indirim_orani = 0
                            # İndirimsiz ürünlerde de devam edelim, veritabanına kaydetmek için
                            sifir_fiyati = indirimli_fiyat
                    except Exception as e:
                        # Normal fiyat bulunamadı, indirim yok
                        logger.info(f"Normal fiyat bulunamadı, indirim yok: {str(e)}")
                        sifir_fiyati = indirimli_fiyat
                        indirim_orani = 0
                        
                except Exception as e:
                    logger.error(f"Fiyat bilgileri alınamadı: {str(e)}")
                    continue
                
                # Kaydetmeye değer mi kontrol et (en azından ürün adı ve fiyat bilgisi olmalı)
                if not urun_adi or indirimli_fiyat <= 0:
                    logger.info(f"Ürün {urun_id} için yeterli bilgi yok, atlanıyor.")
                    continue
                
                # Veritabanına kaydet
                try:
                    kayit_basarili = urun_kaydet(conn, urun_id, urun_adi, urun_linki, 
                                            indirim_orani, sifir_fiyati, indirimli_fiyat)
                    logger.info(f"Ürün veritabanına kaydedildi: {urun_adi}")
                    
                    # İndirim oranı %5'ten fazlaysa bildirim göndermeyi değerlendir
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
                    
                    urun_sayisi += 1
                except Exception as e:
                    logger.error(f"Ürün kaydedilirken hata oluştu: {str(e)}")
                    continue
                
            except Exception as e:
                logger.error(f"Ürün işlenirken hata oluştu: {str(e)}")
                continue
        
        # Daha fazla ürün yükle - hem eski hem yeni yapıyı dene
        try:
            logger.info("Daha fazla ürün yüklemeye çalışılıyor...")
            
            # Sayfanın sonuna kaydır
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            
            # Yeni yapıdaki "Daha fazla ürün" butonunu bulma
            try:
                # Önce eski seçiciyi dene
                load_more_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.moria-LoadMore-button"))
                )
                logger.info("Eski 'Daha fazla ürün' butonu bulundu")
            except:
                # Sonra yeni seçiciyi dene
                try:
                    load_more_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-test-id='load-more-button']"))
                    )
                    logger.info("Yeni 'Daha fazla ürün' butonu bulundu")
                except:
                    # hepsiburada-prd.md'deki seçiciyi dene
                    try:
                        load_more_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.moria-Button-bzoChi"))
                        )
                        logger.info("PRD'deki 'Daha fazla ürün' butonu bulundu")
                    except:
                        logger.info("'Daha fazla ürün' butonu bulunamadı")
                        load_more_button = None
            
            if load_more_button:
                logger.info("'Daha fazla ürün' butonuna tıklanıyor...")
                driver.execute_script("arguments[0].click();", load_more_button)
                time.sleep(5)
                
                # Yeni ürünleri al (hem eski hem yeni yapıyı kontrol et)
                new_urunler = driver.find_elements(By.CSS_SELECTOR, "li.productListContent-zAP0Y5msy8OHn5z7T_K_")
                if not new_urunler:
                    new_urunler = driver.find_elements(By.CSS_SELECTOR, "a.productCardLink-XUJYBO4aGZl6zvMNIzAJ")
                
                logger.info(f"Daha fazla yükleme sonrası {len(new_urunler)} ürün bulundu")
                
                # Yeni ürünleri işle - sadece daha önce işlenmemiş ID'ler
                for yeni_urun_index, yeni_urun in enumerate(new_urunler):
                    yeni_urun_id = yeni_urun.get_attribute('id') or f"yeni_urun_{yeni_urun_index}"
                    if yeni_urun_id not in islenen_urun_idleri:
                        # Burada aynı işleme kodu tekrarlanabilir veya ayrı bir metod çağrılabilir
                        logger.info(f"Yeni yüklenen ürün işleniyor: {yeni_urun_id}")
                        # İşleme kodunu buraya kopyalayabilirsiniz
        
        except Exception as e:
            logger.error(f"Daha fazla ürün yüklenirken hata oluştu: {str(e)}")
        
        logger.info(f"Toplam {urun_sayisi} ürün işlendi. {indirim_urun_sayisi} ürün %5+ indirimli olarak bildirildi.")
        
    except Exception as e:
        logger.error(f"Tarama sırasında hata oluştu: {str(e)}")
        # Hata durumunda sayfa kaynağını kaydet
        if driver:
            try:
                with open(os.path.join(HEPSIBURADA_DIR, "hepsiburada_error_page.html"), "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info("Hata sayfası 'hepsiburada_error_page.html' dosyasına kaydedildi.")
            except Exception as e:
                logger.error(f"Hata sayfası kaydedilemedi: {str(e)}")
    
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