# İnce Memed – LLM Destekli Lemmatizasyon

Bu depo, Yaşar Kemal'in *İnce Memed* külliyatı üzerinde yürütülen
LLM destekli sözlükçülük ön işleme çalışmasının teknik bileşenlerini içerir.

⚠️ **Telif kısıtları** nedeniyle ham metinler ve toplu çıktılar paylaşılmamaktadır.
Paylaşılan içerik, **yöntemin yeniden üretilebilirliğini** hedefler.

---

## Yaklaşımlar

### v1 — JSON Çıktılı Çoklu Analiz (Terk Edildi)

- **Dosyalar:** `YasarKemalSozluk.modelfile`, `ince_memed_v3_checkpoint.py`
- **Çıktı şeması:** `{pdf_sayfa, cumle_id, token, lemma, anlam, etiket, cumle}`
- **Amaç:** Token bazlı lemma, anlam (tanım) ve dilbilgisel etiket üretimi
- **Sonuç:** Yapısal tutarsızlık ve halüsinasyon nedeniyle terk edildi.
  LLM'in aynı anda birden fazla dilbilimsel görev üstlenmesi,
  hem anlam hem etiket kalitesini düşürdü.

### v2 — TSV Çıktılı Salt Lemmatizasyon (Kullanılan)

- **Dosyalar:** `lemmatizer_v3.Modelfile`, `ince_memed_lemmatizer.py`
- **Model:** `qwen3:30b-a3b-instruct-2507-q4_K_M` (Qwen 30B, 4-bit quantized, Ollama ile yerel çalıştırma)
- **Çıktı:** Her satırda `token\tlemma` (TSV)
- **İşleme birimi:** Sayfa bazlı paragraflar, 250 kelimeyi aşan paragraflar otomatik bölünür
- **Sonuç:** elemanTR referansıyla **%80.6 uyum** (ilk 10 sayfa değerlendirmesi)

**v1'den v2'ye geçiş gerekçesi:**
Görev daraltma (çoklu analiz → salt lemmatizasyon) ve çıktı sadeleştirme (JSON → TSV)
ile modelin tek göreve odaklanması sağlanmış, tutarlılık önemli ölçüde artmıştır.
Bu evrim, mevcut yerel LLM'lerin sözlükçülükte hangi görevlerde başarılı
olabileceğini somut biçimde ortaya koymaktadır.

---

## Depo Yapısı

```
sozlukculuk/
├── model/
│   ├── YasarKemalSozluk.modelfile    # v1 — JSON çıktılı (terk edildi)
│   ├── lemmatizer_v2.Modelfile       # v2 erken iterasyon (num_ctx 4096)
│   └── lemmatizer_v3.Modelfile       # v2 son hali (num_ctx 8192)
├── scripts/
│   ├── ince_memed_lemmatizer.py      # Ana işleme scripti (checkpoint destekli)
│   ├── birlestir.py                  # elemanTR + Qwen çıktılarını birleştirme
│   └── degerlendir.py                # Karşılaştırmalı değerlendirme
├── output/
│   ├── qwen_kisa.txt                 # Qwen çıktısı (ilk 10 sayfa, örnek)
│   └── elemantr_kisa.txt             # elemanTR çıktısı (ilk 10 sayfa, örnek)
├── lemma-explorer/                   # Sonuç keşif web uygulaması
└── docs/                             # GitHub Pages
```

---

## Kurulum

```bash
pip install pdfplumber ollama

# v2 modelini oluştur (son iterasyon)
ollama create lemmatizer -f model/lemmatizer_v3.Modelfile
```

## Kullanım

```bash
# Test (ilk 10 sayfa)
python scripts/ince_memed_lemmatizer.py -i metin.txt -o sonuc.txt --pages 10

# Tam çalıştırma (checkpoint destekli, kesintiden sonra kaldığı yerden devam eder)
python scripts/ince_memed_lemmatizer.py -i metin.txt -o sonuc.txt

# Checkpoint sıfırla ve baştan başla
python scripts/ince_memed_lemmatizer.py -i metin.txt -o sonuc.txt --reset

# Değerlendirme
python scripts/degerlendir.py
```

---

## Çıktı Formatı

v2'de her satır bir token–lemma çifti içerir (TSV):

```
Yaşlı	yaşlı
kadın	kadın
oğluna	oğul
seslendi	seslenmek
.	.

Kapıyı	kapı
açıp	açmak
dışarı	dışarı
çıktı	çıkmak
.	.
```

Cümleler arası boş satır, sayfalar arası `|` ayracı kullanılır.

---

## Değerlendirme Sonuçları

### LLM vs Kural Tabanlı Karşılaştırma

| Yöntem | Referans | Uyum |
|--------|----------|------|
| Qwen v2 (num_ctx 8192) | elemanTR | %80.6 |
| Zeyrek (kural tabanlı) | elemanTR | %87.1 |

### Modelfile Evrimi

| | v2 (num_ctx 4096) | v3 (num_ctx 8192) |
|---|---|---|
| Dosya boyutu | 7.0 KB | 7.2 KB |
| Girdi kapasitesi | ~1000 token | ~5051 token |
| İlk 10 sayfa uyumu | %80.7 | %80.6 |
| En kötü blok (s.423-432) | %73.6 | %74.8 |

### Veri Ölçeği

- **Toplam işlenen satır:** 689.575
- **Benzersiz token:** 63.259
- **Benzersiz lemma:** 22.033
- **Sistematik hata oranı (temizlik sonrası):** %3.5

### Qwen Hata Tipleri

- **İlk harf uyumsuzluğu** (babam → aba): ~23.000 token
- **Kiril/İngilizce lemma** (su → су, genç → young): ~477 token

### Zeyrek Analizi

- **Tek sonuçlu doğruluk:** %87.1
- **Belirsiz token oranı:** %40.6
- **Bağlam duyarlı belirsizlik çözme:** %60 (20 cümle testi)
- **Sorunlu alanlar:** Edilgen fiiller, -lI sıfatları

---

## Teknik Özellikler

### Modelfile Tasarımı

Modelfile (sistem iletisi), modelin görevini açıkça sınırlandırır:

- **Görev:** Tokenizasyon + lemmatizasyon (başka bir şey değil)
- **Format:** Kesinlikle TSV (`token\tlemma`)
- **Kurallar:** Fiil çekimleri → mastar, isim çekimleri → yalın, özel isim → büyük harf korunur
- **Yasaklar:** Açıklama, yorum, markdown, tanım yazma

### Checkpoint Mekanizması

Script, her paragraf işlendikten sonra ilerlemeyi kaydeder:
- SSH kopması veya kesintiden sonra `--reset` olmadan çalıştırılınca kaldığı yerden devam eder
- `lemma_durum.json` dosyasından anlık ilerleme izlenebilir
- tmux/nohup ile uzun süreli çalıştırmaya uygun

---

## Amaç

Bu kodlar, nihai sözlük üretimi için değil; LLM'lerin sözlükçülükte
**ön işleme aşamasında** nasıl ve hangi sınırlar içinde kullanılabileceğini
göstermek için tasarlanmıştır.

Çalışmanın temel bulgusu, mevcut yerel LLM'lerin çoklu dilbilimsel
görevleri (lemma + anlam + etiket) aynı anda başarıyla üretemediği,
ancak görev daraltıldığında (salt lemmatizasyon) kural tabanlı
araçlara yakın performans gösterdiğidir.

---

## Lisans & Etik

- Telifli metinler ve elemanTR toplu çıktıları paylaşılmamaktadır
- Yalnızca yöntemin yeniden üretilebilirliğine yönelik teknik bileşenler açık erişimdedir
- Veri egemenliği araştırmacıda kalmıştır (yerel model, üçüncü taraf API kullanılmamıştır)
