#!/usr/bin/env python3
"""
İnce Memed Lemma Gezgini — JSON oluşturucu
============================================
Kullanım:
  pip install zeyrek
  python build_json.py --qwen qwen_sonuc.txt --elemantr elemantr_sonuc.txt

Çıktı:
  qwen.json   — Qwen lemmatizasyon (temizlenmiş)
  zeyrek.json — Zeyrek morfolojik analiz (çoklu olasılık)

JSON formatı: [[token, [lemma1, lemma2, ...], page], ...]
  - index = satır numarası (linenum)
  - token = orijinal kelime
  - lemma listesi
  - page = PDF sayfa numarası
"""

import json, time, argparse, sys, warnings, os

warnings.filterwarnings("ignore")

PUNCT = set('.,!?;:"\'-|()[]{}…–—«»/\\*')


def tr_lower(s):
    """Türkçe uyumlu lowercase — İ→i, I→ı"""
    return s.replace('İ', 'i').replace('I', 'ı').lower()


def is_tr_alpha(s):
    """Sadece Türkçe harf mi?"""
    TR = set('abcçdefgğhıijklmnoöprsştuüvyzâîû')
    return all(c in TR for c in tr_lower(s) if c not in PUNCT and c != ' ')


def parse_result_file(filepath):
    """token\\tlemma dosyasını oku → [(token, lemma, page), ...]"""
    entries = []
    page = 1
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            stripped = line.strip()
            if stripped == '|' or stripped == '|\t|':
                page += 1
                continue
            if not stripped:
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                token = parts[0].strip()
                lemma = parts[1].strip()
                if token:
                    entries.append((token, lemma, page))
    return entries


def build_qwen_json(qwen_path, output='qwen.json'):
    """Qwen sonucunu temizleyerek JSON'a dönüştür"""
    print(f"[Qwen] {qwen_path} okunuyor...")
    raw = parse_result_file(qwen_path)
    print(f"  {len(raw)} entry, {raw[-1][2]} sayfa")

    data = []
    n_error = 0
    n_fixed = 0

    for token, lemma, page in raw:
        is_punct = all(c in PUNCT for c in token)
        if is_punct:
            data.append([token, [lemma], page])
            continue

        t_clean = token.lstrip('"\'([—–-')
        l_clean = lemma.lstrip('"\'([—–-')

        # Kural 1: Lemma Türkçe karakter dışı → hatalı işaretle
        if not is_tr_alpha(l_clean):
            data.append([token, ['⚠' + lemma], page])
            n_error += 1
            continue

        # Kural 2: İlk harf farklı → token'ı lemma olarak kabul et
        if t_clean and l_clean:
            if tr_lower(t_clean)[0] != tr_lower(l_clean)[0]:
                data.append([token, [token], page])
                n_fixed += 1
                continue

        data.append([token, [lemma], page])

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(output) / 1024 / 1024
    print(f"  → {output}: {len(data)} satır, {size:.1f} MB")
    print(f"  Hatalı (⚠): {n_error}, İlk harf düzeltme: {n_fixed}")
    return data


def build_zeyrek_json(elemantr_path, output='zeyrek.json'):
    """Elemantr tokenlarını Zeyrek ile analiz et → JSON"""
    try:
        import logging
        logging.disable(logging.CRITICAL)
        from zeyrek.morphology import MorphAnalyzer
    except ImportError:
        print("HATA: pip install zeyrek")
        sys.exit(1)

    print("Zeyrek başlatılıyor...")
    analyzer = MorphAnalyzer()

    print(f"[Zeyrek] {elemantr_path} okunuyor...")
    raw = parse_result_file(elemantr_path)
    print(f"  {len(raw)} entry, {raw[-1][2]} sayfa")

    unique = set(t for t, l, p in raw)
    print(f"  {len(unique)} benzersiz token analiz ediliyor...")

    cache = {}
    done = 0
    start = time.time()
    for token in unique:
        try:
            results = analyzer._parse(token)
            lemmas = []
            seen = set()
            for a in results:
                if a is not None:
                    lem = a.dict_item.lemma
                    if lem not in seen:
                        lemmas.append(lem)
                        seen.add(lem)
            cache[token] = lemmas if lemmas else [token]
        except Exception:
            cache[token] = [token]
        done += 1
        if done % 10000 == 0:
            print(f"  {done}/{len(unique)}...")

    elapsed = time.time() - start
    print(f"  Zeyrek analizi: {elapsed:.1f}s")

    data = []
    for token, _, page in raw:
        lemmas = cache.get(token, [token])
        data.append([token, lemmas, page])

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

    size = os.path.getsize(output) / 1024 / 1024
    print(f"  → {output}: {len(data)} satır, {size:.1f} MB")
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Lemma Gezgini JSON oluşturucu',
        epilog='Örnek: python build_json.py --qwen qwen_sonuc.txt --elemantr elemantr_sonuc.txt'
    )
    parser.add_argument('--qwen', help='Qwen sonuç dosyası')
    parser.add_argument('--elemantr', help='Elemantr sonuç dosyası (Zeyrek analizi için)')
    parser.add_argument('--outdir', default='.', help='Çıktı dizini')
    args = parser.parse_args()

    if not args.qwen and not args.elemantr:
        print("En az bir dosya belirtin: --qwen ve/veya --elemantr")
        sys.exit(1)

    if args.qwen:
        build_qwen_json(args.qwen, os.path.join(args.outdir, 'qwen.json'))

    if args.elemantr:
        build_zeyrek_json(args.elemantr, os.path.join(args.outdir, 'zeyrek.json'))

    print("\nBitti! JSON dosyalarını index.html ile aynı dizine koyun.")
