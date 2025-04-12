import configparser
import logging
import requests
import time
from typing import Dict, Optional

class TelegramNotifier:
    def __init__(self, config_file: str = 'config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        self.bot_token = self.config.get('Telegram', 'bot_token')
        self.chat_id = self.config.get('Telegram', 'chat_id')
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
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

    def send_product_notification(self, product_data: Dict, marketplace: str) -> bool:
        """
        Send product notification to Telegram channel
        
        Args:
            product_data: Dictionary containing product information
            marketplace: Name of the marketplace (amazon, teknosa, etc.)
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            message = self._format_message(product_data, marketplace)
            return self._send_message(message)
        except Exception as e:
            self.logger.error(f"Error sending notification: {str(e)}")
            return False

    def _format_message(self, product_data: Dict, marketplace: str) -> str:
        """Format the message according to product data and marketplace"""
        
        # Base template
        message = f"""🔥 <b>OUTLET FIRSATI!</b> 🔥
📍 <b>{marketplace.upper()}</b>

✅ {product_data.get('name', 'N/A')}
💰 Normal Fiyat: {product_data.get('original_price', 'N/A')} TL
🏷️ İndirimli Fiyat: {product_data.get('discounted_price', 'N/A')} TL
📉 İndirim Oranı: %{product_data.get('discount_rate', 'N/A')}

🔗 {product_data.get('url', '#')}"""

        return message

    def _send_message(self, message: str) -> bool:
        """Send message to Telegram with retry mechanism"""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    json={
                        'chat_id': self.chat_id,
                        'text': message,
                        'parse_mode': 'HTML',
                        'disable_web_page_preview': True
                    }
                )
                
                if response.status_code == 200:
                    self.logger.info("Telegram bildirimi gönderildi")
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