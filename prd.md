# discountMe Projesi - Ürün Gereksinimleri Dokümanı

## Proje Amacı
Bu proje, popüler e-ticaret platformlarındaki (Amazon, Teknosa, Hepsiburada) büyük indirimleri gerçek zamanlı olarak takip edip, kullanıcılara tercih ettikleri kategoriler bazında Telegram bildirimleri gönderen bir sistemdir.

## Sistem Bileşenleri

### 1. Web Scraper Modülleri
Her bir e-ticaret platformu için özelleştirilmiş, bağımsız çalışan scraper modülleri:

- **amazon/amazon_depo2.py**: Amazon.com.tr için özel hazırlanmış veri çekme modülü
- **teknosa/teknosa_scraper.py**: Teknosa.com için özel hazırlanmış veri çekme modülü
- **hepsiburada/hepsiburada_scraper.py**: Hepsiburada.com için özel hazırlanmış veri çekme modülü

### 2. Bildirim Sistemi
- **telegram_notifier.py**: Tüm platformlardan gelen indirimleri standart formatta iletip, Telegram bildirimleri gönderen modül
- **telegram_bot.py**: Kullanıcı etkileşimleri, kategori tercihleri ve abonelik yönetimini sağlayan Telegram bot arayüzü

### 3. Veritabanı Yapısı
- Ürün veritabanları: Her platform için ayrı SQLite veritabanları (platform_products.db)
- Kullanıcı tercihleri veritabanı: Kullanıcı aboneliklerini kategorilere göre saklayan veritabanı (telegram_preferences.db)

### 4. Başlatıcı ve Entegrasyon
- **start.py**: Tüm scraper modüllerini paralel olarak çalıştıran ana başlatma scripti (daha sonra geliştirilecek)

## Özellikler ve Fonksiyonlar

### Kullanıcı Özellikleri
- Kategori bazlı abonelik sistemi (Elektronik, Moda vb.)
- Platform bazlı abonelik seçenekleri (Amazon, Teknosa, Hepsiburada)
- Kişiselleştirilmiş bildirim tercihleri
- Abonelik yönetimi (ekleme/çıkarma)

### Teknik Özellikler
- Otomatik veri çekme ve analiz
- %25+ indirimli ürünlerin tespiti
- IP ban koruması ve proxy desteği
- Rate limiting ve yeniden deneme mekanizmaları
- Verimli veritabanı yönetimi ile mükerrer bildirim önleme

## Dağıtım ve Operasyon
- **7/24 çalışan sunucu**: VDS üzerinde kesintisiz operasyon
- **Otomasyon**: Çökme durumunda yeniden başlatma ve izleme sistemleri
- **Log yönetimi**: Potansiyel sorunlar için detaylı loglama

## Çalışma Mantığı

1. Sunucu üzerinden programlar başlatılır. (Şu an için ayrı ayrı çalıştırılabilir, ancak ileride yalnızca **start.py** kodunu çalıştırmak yeterli olacaktır.)
2. Tarama işlemi tamamlandıktan sonra 15 dakika beklenir ve ardından tarama tekrar başlatılır.
3. Tespit edilen ürünlerin fiyatları veritabanı ile karşılaştırılır. Eğer bir ürünün fiyatı %25 veya daha fazla düştüyse, bu ürün **telegram_notifier** modülüne gönderilir. Eğer ilgili ürün veritabanında yoksa, ürün veritabanına eklenir ve işlem devam eder.
4. **telegram_notifier** modülü, bu ürünleri standart bir formatta Telegram kanalına iletir.
5. Kullanıcı, ilgili kategoriden bildirim almayı seçtiyse (kategoriye abone olduysa), bu bildirim kullanıcıya ulaştırılır.
6. Tarama sırasında elde edilen sonuçlar, ürün kategorisi bilgisiyle birlikte veritabanına kaydedilir.

### Sistem İyileştirme Notları
- Her bir internet sitesi için aynı yapıda veritabanı oluşturulması önerilir. Bu, sistemin daha pratik ve yönetilebilir olmasını sağlayacaktır.
