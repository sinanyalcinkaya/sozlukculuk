# Methodology – LLM Destekli Ön İşleme Hattı

Bu belge, *İnce Memed* külliyatı üzerinde yürütülen
LLM destekli sözlükçülük ön işleme çalışmasının
teknik yöntemini ve tasarım kararlarını özetler.
Amaç, **çıktıların değil yöntemin** yeniden üretilebilirliğini sağlamaktır.

## 1. Kapsam ve Amaç

Bu çalışma, tam metin bir yazar sözlüğü üretmeyi hedeflemez.
Amaç, yazar sözlükçülüğünde **ön işleme aşamasında**
büyük dil modellerinin (LLM) hangi görevlerde,
hangi sınırlar içinde ve nasıl denetlenerek kullanılabileceğini
yöntemsel olarak göstermektir.

LLM, bu bağlamda:
- nihai karar verici değil,
- taslak üretici ve yardımcı bir bileşen
olarak konumlandırılmıştır.

## 2. Veri Kaynağı ve Derlem Oluşturma

Veri kaynağını Yaşar Kemal’in *İnce Memed* romanının
dört ciltten oluşan külliyatı oluşturmaktadır.
Metinler PDF biçimindedir ve OCR yoluyla ham metin elde edilmiştir.

Telif kısıtları nedeniyle:
- ham metinler,
- tam çıktı dosyaları
paylaşılmamaktadır.

Paylaşılan kodlar, aynı yapıda başka metinlerle
aynı ön işleme hattının kurulmasını mümkün kılar.

## 3. OCR Ön Temizleme

OCR çıktılarında görülen tipik hatalar:
- karakter bozulmaları,
- satır sonu tirelemeleri,
- anlamsız dizgeler,
- sayfa numarası artıklarıdır.

Bu hataları azaltmak için Python tabanlı bir ön temizlik süreci uygulanmıştır.
Bu süreç:
- yalnızca açıkça makine kaynaklı bozulmaları hedef alır,
- ağız özelliklerini ve yazara özgü biçimleri **bilinçli olarak korur**.

Ön temizlik, dil normlaştırma değil,
**gürültü azaltma** amacı taşır.

## 4. Bölütleme Stratejisi

Temizlenmiş metin:
- PDF sayfası,
- cümle
düzeyinde bölütlenmiştir.

Her cümle:
- bağımsız bir LLM çağrısı olarak işlenir,
- `pdf_sayfa` ve `cumle_id` bilgisiyle etiketlenir.

Bu yaklaşım:
- bağlam penceresi taşmalarını önler,
- çıktılar arasında karışmayı engeller,
- izlenebilirliği artırır.

## 5. LLM Ortamı ve Model Yapılandırması

Çalışmada yerel ortamda çalışan açık kaynaklı bir LLM kullanılmıştır.
Model:
- Ollama üzerinden çalıştırılmış,
- 4-bit quantization uygulanmış,
- özel bir `modelfile` ile görevine sınırlandırılmıştır.

Yerel model tercihi:
- veri egemenliği,
- maliyet kontrolü,
- uzun süreli deneme olanağı
sağlamak amacıyla yapılmıştır.

## 6. Prompt Tasarımı ve Modelin Rolü

Modelden yalnızca şu görevler beklenmiştir:
- içerik sözcüğü olup olmadığını belirleme,
- lemma taslağı önerme,
- kısa bağlam-içi anlam üretme,
- sınırlı bir etiket kümesiyle işaretleme.

Modelden:
- tanım yazması,
- sözlük maddesi üretmesi,
- yorumlayıcı açıklamalar yapması
istenmemiştir.

Bu sınırlar, prompt ve modelfile düzeyinde açıkça tanımlanmıştır.

## 7. Çıktı Şeması

Model çıktıları yapılandırılmış biçimde kaydedilir.
Her kayıt şu alanları içerir:

- `pdf_sayfa`
- `cumle_id`
- `token`
- `lemma`
- `anlam`
- `etiket`
- `cumle`

Çıktılar TSV ve JSON biçiminde üretilir.
Bu yapı, hem manuel incelemeye
hem de daha ileri sözlük modellemelerine uygundur.

## 8. Uzun Süreli İşleme ve Checkpoint Mekanizması

Büyük hacimli metinler için:
- her N cümlede otomatik kayıt (checkpoint),
- kesinti sonrası kaldığı yerden devam (resume)
mekanizmaları uygulanmıştır.

Bu yaklaşım, 1000 sayfa ölçeğindeki metinlerin
yerel ortamda güvenli biçimde işlenmesini mümkün kılar.

## 9. Lemmatizasyonun Değerlendirilmesi

LLM tarafından üretilen lemma önerileri
nihai doğruluk olarak kabul edilmemiştir.

Karşılaştırma amacıyla:
- bağımsız,
- yüksek doğruluk oranına sahip,
- henüz açık kaynak olarak yayımlanmamış
bir lemmatizasyon sistemi kullanılmıştır.

Bu sistemin çıktıları paylaşılmamış,
yalnızca hata tipolojisi ve eşleşme oranlarını
gözlemlemek için referans alınmıştır.

## 10. Yeniden Üretilebilirlik ve Etik

Bu depo:
- çıktıları değil,
- **yöntemi**
yeniden üretilebilir kılmayı hedefler.

Paylaşılanlar:
- ön işleme betikleri,
- model yapılandırma dosyası,
- çıktı şeması,
- yöntemsel açıklamalardır.

Bu yaklaşım, telif ve etik kısıtlarla
bilimsel şeffaflık arasında denge kurmayı amaçlar.
