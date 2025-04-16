from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import requests
import sqlite3
import logging
import configparser
from datetime import datetime
from retry import retry
from fake_useragent import UserAgent
from time import sleep
from random import uniform
from concurrent.futures import ThreadPoolExecutor

class Config:
    def __init__(self, config_file='config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
    @property
    def database_path(self):
        return self.config['DATABASE']['Path']
        
    @property
    def telegram_token(self):
        return self.config['TELEGRAM']['BotToken']

# Load configuration
config = Config()

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename='scraper.log'
    )

@retry(tries=3, delay=2)
def setup_driver():
    try:
        chrome_options = Options()
        chrome_options.add_argument("--incognito")
        chrome_options.add_argument("--disable-cache")
        ua = UserAgent()
        chrome_options.add_argument(f'user-agent={ua.random}')
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_argument('--headless')  # Run in headless mode

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.delete_all_cookies()
        driver.execute_cdp_cmd('Network.clearBrowserCache', {})
        driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
        return driver
    except Exception as e:
        logging.error(f"Driver setup failed: {str(e)}")
        raise

@retry(tries=3, delay=2, backoff=2)
def send_telegram_notification(bot_token, chat_id, message):
    response = requests.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        },
        timeout=10
    )
    response.raise_for_status()
    return response

def smart_sleep():
    sleep(uniform(2.0, 5.0))  # Random delay between 2-5 seconds

class AmazonDriver:
    def __init__(self):
        self.driver = None
        
    def __enter__(self):
        self.driver = setup_driver()
        return self.driver
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()

# Database connection
conn = sqlite3.connect(config.database_path)
c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS urunler
             (urun_adi TEXT, urun_linki TEXT, urun_fiyati REAL, urun_sifir_fiyat REAL, urun_asin TEXT, tarih TEXT)''')

# Logging settings
logging.basicConfig(filename=config.config['LOGGING']['Filename'], level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def urun_kaydet(urun_adi, urun_linki, urun_fiyati, urun_sifir_fiyat, urun_asin):
    with sqlite3.connect(config.database_path) as conn:
        c = conn.cursor()
        tarih = time.strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO urunler VALUES (?, ?, ?, ?, ?, ?)", 
                 (urun_adi, urun_linki, urun_fiyati, urun_sifir_fiyat, urun_asin, tarih))

def bulk_save_products(products):
    with sqlite3.connect(config.database_path) as conn:
        c = conn.cursor()
        c.executemany(
            "INSERT INTO urunler VALUES (?, ?, ?, ?, ?, ?)",
            [(p['name'], p['url'], p['price'], p['original_price'], p['asin'], p['date']) 
             for p in products]
        )

def get_last_asin():
    try:
        c.execute("SELECT urun_asin FROM urunler ORDER BY tarih DESC LIMIT 1")
        result = c.fetchone()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Son ASIN getirilirken hata oluştu: {str(e)}")
        return None

class ProductProcessor:
    def __init__(self, config):
        self.config = config
        self.driver = None
        
    def process_product(self, product_element):
        try:
            product_data = self._extract_product_data(product_element)
            if self._is_discounted_enough(product_data):
                self._save_product(product_data)
                self._notify_telegram(product_data)
        except Exception as e:
            logging.error(f"Ürün işleme hatası: {str(e)}")

def is_discounted_enough(current_price, original_price, min_discount_percentage=20):
    if not original_price or original_price <= 0:
        return False
    discount_percentage = ((original_price - current_price) / original_price) * 100
    return discount_percentage >= min_discount_percentage

def get_products(driver, url):
    try:
        driver.get(url)
        time.sleep(3)  # Page load wait
        
        while True:  # Scan all pages
            tum_urunler = driver.find_elements(By.CSS_SELECTOR, 'div[data-component-type="s-search-result"]')
            
            if not tum_urunler:
                logging.warning("Ürün listesi bulunamadı")
                break
                
            # Process products
            for urun in tum_urunler:
                try:
                    urun_linki = urun.find_element(By.CSS_SELECTOR, 'a.a-link-normal').get_attribute('href')
                    urun_adi = urun.find_element(By.CSS_SELECTOR, 'span.a-text-normal').text
                    
                    # Fiyat bilgilerini al
                    try:
                        fiyat_element = urun.find_element(By.CSS_SELECTOR, '.a-price .a-offscreen')
                        urun_fiyati = float(fiyat_element.text.replace('TL', '').replace('.', '').replace(',', '.').strip())
                        
                        # Orijinal fiyatı al
                        original_price_element = urun.find_element(By.CSS_SELECTOR, '.a-price.a-text-price .a-offscreen')
                        urun_sifir_fiyat = float(original_price_element.text.replace('TL', '').replace('.', '').replace(',', '.').strip())
                    except Exception as e:
                        logging.error(f"Fiyat çekme hatası: {str(e)}")
                        continue
                    
                    # ASIN bilgisini al
                    try:
                        urun_asin = urun.get_attribute('data-asin')
                    except:
                        continue
                        
                    # İndirim kontrolü
                    if is_discounted_enough(urun_fiyati, urun_sifir_fiyat):
                        # Ürünü kaydet
                        urun_kaydet(urun_adi, urun_linki, urun_fiyati, urun_sifir_fiyat, urun_asin)
                        
                        # Telegram bildirimi gönder
                        message = (
                            f"🔥 Yeni İndirimli Ürün!\n\n"
                            f"📦 {urun_adi}\n"
                            f"💰 Güncel Fiyat: {urun_fiyati:.2f} TL\n"
                            f"📈 Normal Fiyat: {urun_sifir_fiyat:.2f} TL\n"
                            f"🔗 {urun_linki}"
                        )
                        send_telegram_notification(config.telegram_token, config.config['TELEGRAM']['ChatId'], message)
                    
                except Exception as e:
                    logging.error(f"Ürün işleme hatası: {str(e)}")
                    continue
                    
            # Next page check
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, '.s-pagination-next:not(.s-pagination-disabled)')
                next_button.click()
                time.sleep(3)
            except Exception as e:
                logging.info("Son sayfaya ulaşıldı")
                break
                
    except Exception as e:
        logging.error(f"Sayfa işleme hatası: {str(e)}")
    finally:
        try:
            if driver:
                driver.quit()
        except Exception as e:
            logging.error(f"Driver kapatma hatası: {str(e)}")

def process_pages(urls):
    with ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(get_products, [setup_driver() for _ in range(len(urls))], urls)

# Ana fonksiyon
def main():
    setup_logging()
    urls = [
        "https://www.amazon.com.tr/s?srs=44219324031&bbn=44219324031&rh=n%3A44219324031%2Cn%3A12466496031&pf_rd_i=44219324031&pf_rd_m=A1UNQM1SR2CHM&pf_rd_p=bcc88ca7-b7df-4b17-899c-41df4a987cde&pf_rd_r=PRCNQ64CD246KBBHEDPT&pf_rd_s=merchandised-search-14&ref=TR_AW_CAT_3"
    ]
    
    try:
        process_pages(urls)
    except KeyboardInterrupt:
        logging.info("Program kullanıcı tarafından durduruldu")
    except Exception as e:
        logging.error(f"Program hatası: {str(e)}")
    finally:
        logging.info("Program sonlandı")

if __name__ == "__main__":
    main()
