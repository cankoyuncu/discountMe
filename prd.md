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

## İleride Gelecek Özellikler
- Web arayüzü entegrasyonu
- Trend analizi ve fiyat geçmişi görüntüleme
- Daha fazla e-ticaret platformu desteği (Trendyol, MediaMarkt vb.)
- Fiyat hedef bildirimleri
- Çok dil desteği




