5.03.2025

start.py -> amazon, teknosa, hepsiburada dosyalarının hepsini aynı anda başlatır. 
YAPILMADI EN SON YAPILACAK.

amazon -> selector +
teknosa -> selector +
hepsiburada -> selector +

telegram.py -> amazon, teknosa, hepsiburada üzerinden gelen istekler buradan kanala yönlendirilir. +

su an yasanan problem:
aynı ürünü tarıyor defalarca. ör: 10 kez + 
aynı ürünü birden fazla kez paylasiyor telegram üzerinden. ör: 5 kez +

12.03.2025

Logdan tespit edilen hata: ERROR - Yanit icerigi: {"ok":false,"error_code":429,"description":"Too Many Requests: retry after 29","parameters":{"retry_after":29}} +

Çözüm: İndirim oranı arttırarak çözülebilir. 
Ürün tespit edildikten sonra kuyruğa alınabilir. Ör: 30saniyelik 

hepsiburada: Sayfada 36 adet ürün bulundu. 
             Toplam 0 ürün işlendi. 0 ürün %25+ indirimli. +

Haftaya Tamamlanması Beklenenler: hepsiburada çözülsün. 

19.03.2025

Hepsiburada tarama başarılı, ürünler taranıyor. Loglara düşüyor. Veritabanına yazılıyor. Sayfa geçişinde hata var.

Telegram arayüzü hazırlansın. (Alternatif olarak websiteme entegre etmeyi deneyebilirim.)

09.04.2025
Telegram arayüz ve kategori özelinde ayırmalar yapıldı fakat henüz bitmedi: telegram_preferences.db

Bot arayüzü bitmiş olsun. 
Sunucu alınacak: https://sunucumfix.com/vds-sunucu-kirala
Bot sürekli calisir hale getirelecek.
Loglardan ip ban yenilen zamanlar tespit edilip ona göre proxy kullanımı gerekecek.

rapor sunumu olacak haftaya

16.04.2025

