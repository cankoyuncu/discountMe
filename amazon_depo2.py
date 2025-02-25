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

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

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

# Database connection
conn = sqlite3.connect(config['DATABASE']['Path'])
c = conn.cursor()

# Create table
c.execute('''CREATE TABLE IF NOT EXISTS urunler
             (urun_adi TEXT, urun_linki TEXT, urun_fiyati REAL, urun_sifir_fiyat REAL, urun_asin TEXT, tarih TEXT)''')

# Logging settings
logging.basicConfig(filename=config['LOGGING']['Filename'], level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def urun_kaydet(urun_adi, urun_linki, urun_fiyati, urun_sifir_fiyat, urun_asin):
    tarih = time.strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO urunler VALUES (?, ?, ?, ?, ?, ?)", (urun_adi, urun_linki, urun_fiyati, urun_sifir_fiyat, urun_asin, tarih))
    conn.commit()

def get_last_asin():
    try:
        c.execute("SELECT urun_asin FROM urunler ORDER BY tarih DESC LIMIT 1")
        result = c.fetchone()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"Son ASIN getirilirken hata oluştu: {str(e)}")
        return None

def get_products(driver, url):
    try:
        driver.get(url)
        time.sleep(3)  # Sayfa yüklenme bekleme
        
        while True:  # Tüm sayfaları tarama
            # Ürün listesi
            tum_urunler = driver.find_elements(By.CSS_SELECTOR, 'div[data-component-type="s-search-result"]')
            
            if not tum_urunler:
                logging.warning("Ürün listesi bulunamadı")
                break
                
            for urun in tum_urunler:
                try:
                    # Ürün adı için birden fazla seçici deneme
                    urun_adi = None
                    selectors = [
                        '#search > div.s-desktop-width-max.s-desktop-content.s-opposite-dir.s-wide-grid-style.sg-row > div.sg-col-20-of-24.s-matching-dir.sg-col-16-of-20.sg-col.sg-col-8-of-12.sg-col-12-of-16 > div > span.rush-component.s-latency-cf-section > div.s-main-slot.s-result-list.s-search-results.sg-row > div:nth-child(6) > div > div > span > div > div > div.a-section.a-spacing-small.puis-padding-left-small.puis-padding-right-small > div.a-section.a-spacing-none.a-spacing-top-small.s-title-instructions-style > a > h2'
                        'span.a-size-base-plus.a-color-base.a-text-normal',
                        'h2.a-size-base-plus.a-spacing-none.a-color-base.a-text-normal > span',
                        'span.a-size-medium.a-color-base.a-text-normal',
                        'a.a-link-normal.s-underline-text.s-underline-link-text.s-link-style.a-text-normal',
                        '.a-size-base-plus',
                        'h2 span.a-text-normal'
                    ]
                    
                    for selector in selectors:
                        try:
                            element = urun.find_element(By.CSS_SELECTOR, selector)
                            if element and element.text.strip():
                                urun_adi = element.text.strip()
                                break
                        except:
                            continue

                    if not urun_adi:
                        print("Urun adi bulunamadi - tüm seçiciler denendi")
                        continue
                        
                    print(f"Incelenen urun adi: {urun_adi}")
                    print("--------------------------------")

                    time.sleep(5)

                    try:
                        urun_linki = urun.find_element(By.CSS_SELECTOR, 'a.a-link-normal.s-no-outline').get_attribute('href')
                        print(f"Link: {urun_linki}")

                    except:
                        try:
                            urun_linki = urun.find_element(By.CSS_SELECTOR, 'a[class*="a-link-normal"][href*="/dp/"]').get_attribute('href')
                        except:
                            print("Urun linki bulunamadi")
                            continue

                    try:
                        driver.execute_script(f"window.open('{urun_linki}');")
                        driver.switch_to.window(driver.window_handles[-1])

                        wait = WebDriverWait(driver, 10)
                        wait.until(lambda driver: driver.execute_script('return document.readyState') == 'complete')
                        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                        try:
                            print("Ikinci el fiyati araniyor...")
                            wait = WebDriverWait(driver, 10)
                            
                            selectors = [
                                "span.a-price-whole",
                                ".a-price .a-offscreen",
                                "#priceblock_ourprice",
                                "#priceblock_dealprice"
                            ]
                            
                            urun_fiyati = None
                            for selector in selectors:
                                try:
                                    element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector))) 
                                    if element and element.text.strip():
                                        urun_fiyati = element.text.replace('.', '').strip()
                                        break
                                except:
                                    continue
                            
                            if not urun_fiyati:
                                raise Exception("Depo fiyati bulunamadi")
                            
                            print(f"Depo fiyati: {urun_fiyati} TL")
                        
                        except Exception as e:
                            print(f"Depo fiyat bulma hatasi: {str(e)}")
                            continue

                        try:
                            urun_asin = driver.find_element(By.ID, 'ASIN').get_attribute('value')
                            print("ASIN araniyor...")
                            if not urun_asin:
                                try:
                                    urun_linki_parcalari = urun_linki.split('/')
                                    dp_index = urun_linki_parcalari.index('dp')
                                    if dp_index < len(urun_linki_parcalari) - 1:
                                        urun_asin = urun_linki_parcalari[dp_index + 1]
                                except ValueError:
                                    pass
                            if not urun_asin:
                                raise Exception("ASIN bulunamadi")    
                        except Exception as e:
                            print(f"ASIN bulma hatasi: {str(e)}")
                            continue

                        try:
                            print(f"Sifir fiyati araniyor: {urun_asin}")
                            driver.get(f"https://www.amazon.com.tr/dp/{urun_asin}")
                            
                            wait = WebDriverWait(driver, 5)
                            
                            price_element = wait.until(EC.visibility_of_element_located((
                                By.CSS_SELECTOR, 
                                "#corePriceDisplay_desktop_feature_div > div.a-section.a-spacing-none.aok-align-center.aok-relative > span.a-price.aok-align-center.reinventPricePriceToPayMargin.priceToPay > span:nth-child(2) > span.a-price-whole"
                            )))
                            urun_sifir_fiyat = price_element.text.strip()
                            
                            if not urun_sifir_fiyat:
                                raise Exception("Sifir fiyati bulunamadi")
                                
                        except Exception as e:
                            print(f"Sifir Fiyat bulma hatasi: {str(e)}")
                            continue

                        urun_sifir_fiyat = urun_sifir_fiyat.replace(' TL', '')

                        ikinci_el = float(urun_fiyati.replace('.', '').replace(',', '.'))
                        sifir = float(urun_sifir_fiyat.replace('.', '').replace(',', '.'))

                        if ikinci_el < (sifir * 0.80):
                            mesaj = (
                                "🔥 INDIRIMLI ÜRÜN BULUNDU! 🔥\n"
                                "\n"               
                                f"📦 Urun: {urun_adi}\n"
                                f"💰 İkinci el fiyatı: {ikinci_el} TL\n"
                                f"💰 Sifir fiyati: {sifir} TL\n"
                                f"🏷️ İndirim orani: %{int(((sifir - ikinci_el) / sifir) * 100)}\n"
                                f"💰 İndirim miktari: {sifir - ikinci_el} TL\n"
                                f"🔗 Urun linki: {urun_linki}\n"
                                "================================"
                            )
                            
                            print(mesaj)
                            
                            try:
                                bot_token = config['TELEGRAM']['BotToken']
                                chat_id = config['TELEGRAM']['ChatID']
                                
                                telegram_api_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'

                                max_retries = 2
                                retry_count = 0

                                while retry_count < max_retries:
                                    try:
                                        response = requests.post(
                                            telegram_api_url,
                                            json={
                                                'chat_id': chat_id,
                                                'text': mesaj,
                                                'parse_mode': 'HTML'
                                            },
                                            timeout=10 
                                        )

                                        if response.status_code == 200:
                                            print("Telegram mesaji basariyla gonderildi.")
                                            break
                                        else:
                                             print(f"Telegram API hatasi: {response.status_code} - {response.text}")

                                    except requests.exceptions.RequestException as e:
                                        print(f"Network error: {str(e)}")
                                        retry_count += 1
                                        if retry_count == max_retries:
                                            print("Maksimum yeniden denemeye ragmen mesaj gonderilemedi")
                                        time.sleep(5)
                                    
                            except Exception as e:
                                print(f"Telegram bot hatasi: {str(e)}")

                        else:
                            print("Urun fiyati %20 indirimli degil")
                            print("================================")

                        urun_kaydet(urun_adi, urun_linki, ikinci_el, sifir, urun_asin)

                    except:
                        print("Yeni sekme acilamadi")
                        continue

                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])

                except Exception as e:
                    logging.error(f"Ürün işleme hatası: {str(e)}")

                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue

            # Sonraki sayfa kontrolü
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, '.s-pagination-next:not(.s-pagination-disabled)')
                next_button.click()
                time.sleep(3)
            except:
                logging.info("Son sayfaya ulaşıldı")
                break
                
    except Exception as e:
        logging.error(f"Sayfa işleme hatası: {str(e)}")

# Ana fonksiyon
def main():
    setup_logging()
    driver = setup_driver()
    url = "https://www.amazon.com.tr/s?srs=44219324031&bbn=44219324031&rh=n%3A44219324031%2Cn%3A12466496031&pf_rd_i=44219324031&pf_rd_m=A1UNQM1SR2CHM&pf_rd_p=bcc88ca7-b7df-4b17-899c-41df4a987cde&pf_rd_r=PRCNQ64CD246KBBHEDPT&pf_rd_s=merchandised-search-14&ref=TR_AW_CAT_3"
    
    try:
        get_products(driver, url)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
