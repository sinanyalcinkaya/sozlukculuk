# İnce Memed – LLM Destekli Ön İşleme ve Söz Varlığı Çıkarımı

Bu depo, Yaşar Kemal’in *İnce Memed* külliyatı üzerinde yürütülen
LLM destekli sözlükçülük ön işleme çalışmasının teknik bileşenlerini içerir.

⚠️ Telif kısıtları nedeniyle ham metinler ve toplu çıktılar paylaşılmamaktadır.
Paylaşılan içerik, **yöntemin yeniden üretilebilirliğini** hedefler.

## İçerik

- OCR sonrası metin temizleme ve doğrulama
- Sayfa ve cümle düzeyinde bölütleme
- LLM ile içerik sözcüğü, lemma, anlam ve etiket taslağı üretimi
- Checkpoint / resume destekli uzun süreli işleme

## Kurulum

```bash
pip install pdfplumber ollama
ollama create yasar-sozluk -f YasarKemalSozluk.modelfile

## Kullanım
# Test (ilk 10 cümle)
python ince_memed_v3_checkpoint.py --test-sentences 10

# Tam çalıştırma
python ince_memed_v3_checkpoint.py --full

##Çıktı Şeması

Her kayıt şu alanları içerir:

pdf_sayfa | cumle_id | token | lemma | anlam | etiket | cumle

## Amaç

Bu kodlar, nihai sözlük üretimi için değil; LLM’lerin sözlükçülükte ön işleme aşamasında
nasıl ve hangi sınırlar içinde kullanılabileceğini göstermek için tasarlanmıştır.
