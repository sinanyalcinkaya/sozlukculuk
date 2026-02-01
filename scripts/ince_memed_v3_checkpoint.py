#!/usr/bin/env python3
"""
İnce Memed Söz Varlığı Çıkarıcı v3 - Checkpoint Edition

Yeni özellikler:
- Her 10 cümlede otomatik kayıt (checkpoint)
- Varolan dosyadan devam etme (resume)
- Hata durumunda kaldığı yerden devam

Değişiklikler:
- System prompt Modelfile'da gömülü (yasar-sozluk modeli)
- Her cümle tek tek işlenir (karışma yok)
- Word boundary kontrolü (halüsinasyon önleme)
- PDF sayfa numarası (kitap sayfa no yerine)

Kurulum:
    ollama create yasar-sozluk -f YasarKemalSozluk.modelfile

Kullanım:
    # Hızlı test (ilk 10 cümle)
    python ince_memed_v3_checkpoint.py --test-sentences 10
    
    # Sayfa testi
    python ince_memed_v3_checkpoint.py --test 5
    
    # Tam çalıştırma
    python ince_memed_v3_checkpoint.py --full
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field

import pdfplumber
import ollama

# ============== CONFIGURATION ==============

@dataclass
class Config:
    model: str = "yasar-sozluk"  # Modelfile ile oluşturulan özel model
    temperature: float = 0.2
    checkpoint_interval: int = 10  # Her kaç cümlede bir kayıt
    
    # Stop list
    stop_words: set = field(default_factory=lambda: {
        # Edatlar
        'için', 'gibi', 'ile', 'kadar', 'üzere', 'doğru', 'karşı', 'göre',
        'dek', 'değin', 'beri', 'yana', 'rağmen', 'karşın', 'önce', 'sonra',
        'dolayı', 'ötürü', 'üzerine', 'hakkında', 'dair',
        # Bağlaçlar
        've', 'veya', 'ya', 'yahut', 'ama', 'fakat', 'ancak', 'lakin',
        'oysa', 'halbuki', 'çünkü', 'zira', 'ki', 'de', 'da', 'bile',
        'dahi', 'hem', 'ne', 'ise', 'madem', 'eğer', 'şayet', 'yani',
        # Zamirler
        'ben', 'sen', 'biz', 'siz', 'bu', 'şu', 'o', 'bunlar', 'şunlar',
        'onlar', 'kim', 'ne', 'hangi', 'kendi', 'hep', 'hiç',
        # Soru / belirsizlik
        'mı', 'mi', 'mu', 'mü', 'değil',
        'bir', 'her', 'bazı', 'birkaç', 'hiçbir',
        # Derece zarfları
        'daha', 'çok', 'pek', 'en', 'az', 'biraz', 'epey', 'gayet', 'fazla',
    })

CONFIG = Config()

# ============== PDF EXTRACTION ==============

def preprocess_text(text: str) -> str:
    """OCR düzeltmeleri"""
    text = text.replace('Đ', 'İ').replace('đ', 'i')
    text = text.replace('р', 'r').replace('а', 'a')  # Kiril
    text = re.sub(r'[ \t]+', ' ', text)
    return text


def extract_sentences_from_pdf(pdf_path: str, start_page: int = 0, end_page: int = None, 
                                max_sentences: int = None) -> list[dict]:
    """
    PDF'den cümleleri çıkar.
    Returns: [{"pdf_sayfa": 5, "cumle": "..."}, ...]
    """
    sentences = []
    sentence_id = 0
    
    with pdfplumber.open(pdf_path) as pdf:
        if end_page is None:
            end_page = len(pdf.pages)
        
        for page_idx in range(start_page, min(end_page, len(pdf.pages))):
            text = pdf.pages[page_idx].extract_text() or ""
            if not text.strip():
                continue
            
            pdf_sayfa = page_idx + 1  # 1-indexed
            
            # Pre-processing
            text = preprocess_text(text)
            
            # Satır sonu tire birleştirme
            text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
            
            # Satır içi sayfa numaralarını temizle
            text = re.sub(r'\n\s*\d{1,4}\s*\n', '\n', text)
            
            # Satır sonlarını boşluğa çevir
            text = re.sub(r'\n+', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            
            # Cümlelere böl
            raw_sentences = re.split(r'(?<=[.!?])\s+', text)
            
            for sent in raw_sentences:
                sent = sent.strip()
                # Geçerli cümle mi?
                if len(sent) > 15 and re.search(r'[a-zA-ZçÇğĞıİöÖşŞüÜ]{4,}', sent):
                    sentence_id += 1
                    sentences.append({
                        "cumle_id": sentence_id,
                        "pdf_sayfa": pdf_sayfa,
                        "cumle": sent
                    })
                    
                    # Max sentence kontrolü
                    if max_sentences and len(sentences) >= max_sentences:
                        return sentences
    
    return sentences


# ============== LLM PROCESSING ==============

def process_single_sentence(sentence: str, model: str) -> dict:
    """
    Tek cümleyi işle. System prompt modelde gömülü.
    """
    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "user", "content": sentence}
            ],
            format="json",
            options={
                "temperature": CONFIG.temperature,
                "num_predict": 1500
            }
        )
        
        raw_output = response['message']['content']
        
        try:
            data = json.loads(raw_output)
            return {
                "success": True,
                "tokens": data.get("tokens", []),
                "raw": raw_output
            }
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON parse: {e}", "raw": raw_output}
            
    except Exception as e:
        return {"success": False, "error": str(e), "raw": ""}


def validate_token_in_sentence(token: str, sentence: str) -> bool:
    """
    Token cümlede KELIME olarak var mı? (substring değil)
    """
    token_lower = token.lower().strip()
    sentence_lower = sentence.lower()
    
    # Boş token
    if not token_lower:
        return False
    
    # Word boundary ile kontrol
    # Türkçe karakterleri de kelime sınırı olarak kabul et
    pattern = r'(?<![a-zA-ZçÇğĞıİöÖşŞüÜ])' + re.escape(token_lower) + r'(?![a-zA-ZçÇğĞıİöÖşŞüÜ])'
    return bool(re.search(pattern, sentence_lower))


def filter_and_validate_tokens(tokens: list[dict], sentence: str) -> list[dict]:
    """Token'ları filtrele ve doğrula"""
    validated = []
    
    for t in tokens:
        token_text = t.get("token", "").strip()
        lemma = t.get("lemma", "").lower().rstrip("-")
        
        # Stop word kontrolü
        if lemma in CONFIG.stop_words or token_text.lower() in CONFIG.stop_words:
            continue
        
        # Çok kısa
        if len(token_text) < 2:
            continue
        
        # Sadece noktalama
        if re.match(r'^[.,!?;:"\'\-]+$', token_text):
            continue
        
        # Cümlede gerçekten var mı?
        if not validate_token_in_sentence(token_text, sentence):
            continue
        
        validated.append(t)
    
    return validated


# ============== MAIN PROCESSOR ==============

class SozVarligiProcessor:
    def __init__(self, model: str = CONFIG.model, output_prefix: str = "ince_memed_sozluk"):
        self.model = model
        self.output_prefix = output_prefix
        self.results = []
        self.cumle_counter = 0
        self.processed_count = 0  # Bu session'da işlenen cümle sayısı
        self.stats = {
            "toplam_cumle": 0,
            "toplam_token": 0,
            "basarili_cumle": 0,
            "hatali_cumle": 0,
            "etiket_dagilimi": {}
        }
    
    def load_checkpoint(self, json_file: str) -> bool:
        """Varolan checkpoint'i yükle"""
        if not os.path.exists(json_file):
            return False
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.results = data.get("data", [])
            self.stats = data.get("meta", {}).get("stats", self.stats)
            
            # Cumle counter'ı güncelle
            if self.results:
                self.cumle_counter = max(r["cumle_id"] for r in self.results)
            
            print(f"📂 Checkpoint yüklendi: {len(self.results)} kayıt, son ID: {self.cumle_counter}")
            return True
        except Exception as e:
            print(f"⚠️  Checkpoint yükleme hatası: {e}")
            return False
    
    def get_processed_sentence_ids(self) -> set:
        """İşlenmiş cümle ID'lerini döndür"""
        return {r["cumle_id"] for r in self.results}
    
    def save_checkpoint(self):
        """Mevcut durumu kaydet"""
        json_file = f"{self.output_prefix}.json"
        tsv_file = f"{self.output_prefix}.tsv"
        
        self.export_json(json_file, silent=True)
        self.export_tsv(tsv_file, silent=True)
        print(f"      💾 Checkpoint kaydedildi ({len(self.results)} kayıt)")
    
    def process_sentence(self, sent_data: dict) -> dict:
        """Tek cümle işle"""
        pdf_sayfa = sent_data["pdf_sayfa"]
        cumle = sent_data["cumle"]
        cumle_id = sent_data["cumle_id"]
        
        result = process_single_sentence(cumle, self.model)
        
        if result["success"]:
            tokens = filter_and_validate_tokens(result.get("tokens", []), cumle)
            
            # Etiket istatistiği
            for t in tokens:
                etiket = t.get("etiket", "") or "STANDART"
                self.stats["etiket_dagilimi"][etiket] = \
                    self.stats["etiket_dagilimi"].get(etiket, 0) + 1
            
            self.stats["basarili_cumle"] += 1
            self.stats["toplam_token"] += len(tokens)
            
            return {
                "pdf_sayfa": pdf_sayfa,
                "cumle_id": cumle_id,
                "cumle": cumle,
                "tokens": tokens
            }
        else:
            self.stats["hatali_cumle"] += 1
            return None
    
    def process_sentences(self, sentences: list[dict], verbose: bool = True):
        """Cümle listesini işle"""
        # Checkpoint yükle
        json_file = f"{self.output_prefix}.json"
        checkpoint_loaded = self.load_checkpoint(json_file)
        
        processed_ids = self.get_processed_sentence_ids()
        
        # Henüz işlenmemiş cümleleri filtrele
        remaining_sentences = [s for s in sentences if s["cumle_id"] not in processed_ids]
        
        if checkpoint_loaded and not remaining_sentences:
            print(f"✅ Tüm cümleler zaten işlenmiş!")
            self.print_stats()
            return
        
        total = len(sentences)
        remaining_count = len(remaining_sentences)
        already_processed = total - remaining_count
        
        start_time = time.time()
        
        print(f"\n🚀 İşlem başlıyor...")
        print(f"   Model: {self.model}")
        print(f"   Toplam cümle: {total}")
        if checkpoint_loaded:
            print(f"   ✅ Zaten işlenmiş: {already_processed}")
            print(f"   🔄 İşlenecek: {remaining_count}")
        print("=" * 60)
        
        for i, sent_data in enumerate(remaining_sentences):
            sent_start = time.time()
            
            result = self.process_sentence(sent_data)
            
            sent_time = time.time() - sent_start
            elapsed = time.time() - start_time
            
            if result and result["tokens"]:
                self.results.append(result)
            
            self.processed_count += 1
            
            if verbose:
                status = f"✅ {len(result['tokens'])} token" if result else "❌ Hata"
                eta = (elapsed / self.processed_count) * (remaining_count - self.processed_count)
                
                cumle_short = sent_data["cumle"][:50]
                current_index = already_processed + self.processed_count
                print(f"[{current_index}/{total}] {status} ({sent_time:.1f}s) | "
                      f"S.{sent_data['pdf_sayfa']} | {cumle_short}...")
                
                # Her 10 cümlede checkpoint kaydet
                if self.processed_count % CONFIG.checkpoint_interval == 0:
                    self.save_checkpoint()
                    print(f"      📊 Toplam: {len(self.results)} kayıt, "
                          f"{self.stats['toplam_token']} token | ETA: {eta:.0f}s")
        
        # Son checkpoint
        self.save_checkpoint()
        
        self.stats["toplam_cumle"] = total
        
        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"✅ TAMAMLANDI! {total_time:.1f} saniye")
        self.print_stats()
    
    def print_stats(self):
        """İstatistikleri yazdır"""
        print(f"\n📊 İSTATİSTİKLER")
        print(f"   Toplam cümle: {self.stats['toplam_cumle']}")
        print(f"   Başarılı: {self.stats['basarili_cumle']}")
        print(f"   Hatalı: {self.stats['hatali_cumle']}")
        print(f"   Toplam token: {self.stats['toplam_token']}")
        print(f"   Toplam kayıt: {len(self.results)}")
        print(f"\n   Etiket dağılımı:")
        for etiket, count in sorted(self.stats["etiket_dagilimi"].items(), 
                                     key=lambda x: -x[1]):
            print(f"      {etiket or '(boş)'}: {count}")
    
    def export_json(self, output_file: str, silent: bool = False):
        """JSON olarak dışa aktar"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "meta": {
                    "model": self.model,
                    "stats": self.stats
                },
                "data": self.results
            }, f, ensure_ascii=False, indent=2)
        if not silent:
            print(f"\n📁 JSON: {output_file}")
    
    def export_tsv(self, output_file: str, silent: bool = False):
        """TSV olarak dışa aktar"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("pdf_sayfa\tcumle_id\ttoken\tlemma\tanlam\tetiket\tcumle\n")
            
            for record in self.results:
                for token in record["tokens"]:
                    cumle_clean = record["cumle"].replace("\t", " ").replace("\n", " ")[:100]
                    f.write(f"{record['pdf_sayfa']}\t"
                           f"{record['cumle_id']}\t"
                           f"{token.get('token', '')}\t"
                           f"{token.get('lemma', '')}\t"
                           f"{token.get('anlam', '')}\t"
                           f"{token.get('etiket', '')}\t"
                           f"{cumle_clean}\n")
        
        if not silent:
            print(f"📁 TSV: {output_file}")


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description='İnce Memed Söz Varlığı Çıkarıcı v3 - Checkpoint Edition')
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--test-sentences', type=int, metavar='N',
                       help='Test: ilk N cümleyi işle')
    group.add_argument('--test', type=int, metavar='N',
                       help='Test: ilk N PDF sayfasını işle')
    group.add_argument('--full', action='store_true',
                       help='Tam çalıştırma')
    
    parser.add_argument('--input', '-i',
                        default='ince_memed.pdf',
                        help='Giriş PDF dosyası')
    parser.add_argument('--output', '-o', default='ince_memed_sozluk',
                        help='Çıkış dosya adı (uzantısız)')
    parser.add_argument('--model', '-m', default=CONFIG.model,
                        help=f'Ollama model (default: {CONFIG.model})')
    parser.add_argument('--checkpoint-interval', type=int, default=CONFIG.checkpoint_interval,
                        help=f'Her kaç cümlede checkpoint (default: {CONFIG.checkpoint_interval})')
    
    args = parser.parse_args()
    
    # Checkpoint interval güncelle
    CONFIG.checkpoint_interval = args.checkpoint_interval
    
    # Model kontrolü
    print(f"🔍 Model kontrol: {args.model}")
    try:
        ollama.show(args.model)
        print(f"   ✅ Model mevcut")
    except:
        print(f"   ❌ Model bulunamadı!")
        print(f"   Önce modeli oluşturun:")
        print(f"   ollama create yasar-sozluk -f YasarKemalSozluk.modelfile")
        sys.exit(1)
    
    processor = SozVarligiProcessor(model=args.model, output_prefix=args.output)
    
    if args.test_sentences:
        print(f"\n🧪 TEST: İlk {args.test_sentences} cümle")
        sentences = extract_sentences_from_pdf(args.input, max_sentences=args.test_sentences)
        processor.process_sentences(sentences)
        
    elif args.test:
        print(f"\n🧪 TEST: İlk {args.test} PDF sayfası")
        sentences = extract_sentences_from_pdf(args.input, start_page=0, end_page=args.test)
        processor.process_sentences(sentences)
        
    elif args.full:
        print("\n🚀 TAM ÇALIŞTIRMA")
        sentences = extract_sentences_from_pdf(args.input)
        processor.process_sentences(sentences)


if __name__ == '__main__':
    main()
