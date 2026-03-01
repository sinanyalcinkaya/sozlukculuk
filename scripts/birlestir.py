#!/usr/bin/env python3
"""
İki lemmatizasyon sonuç dosyasını (elemantr master, qwen slave) birleştirir.
Sayfa ayracı (|) ile sayfa eşleştirmesi, sayfa içi ileri-geri token hizalama.

Kullanım: python birlestir.py
Girdi: elemantr_sonuc.txt, qwen_sonuc.txt (aynı dizinde)
Çıktı: birlesik.tsv

Bağımlılık: pip install tqdm
"""

import os
import time
from multiprocessing import Pool, cpu_count

try:
    from tqdm import tqdm
except ImportError:
    os.system("pip install tqdm --break-system-packages -q")
    from tqdm import tqdm


# ─── Dosya okuma & sayfa bölme ────────────────────────────────

def parse_file(filepath):
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                entries.append((parts[0], parts[1]))
            elif len(parts) == 1 and parts[0].strip():
                entries.append((parts[0], ""))
    return entries


def split_pages(entries):
    pages = []
    current = []
    for tok, lemma in entries:
        if tok == "|":
            pages.append(current)
            current = []
        else:
            current.append((tok, lemma))
    if current:
        pages.append(current)
    return pages


def first_meaningful_tokens(page, n=3):
    PUNCT = set('.,!?;:"\'-|()[]{}…–—')
    result = []
    for tok, _ in page:
        if tok not in PUNCT and not all(c in PUNCT for c in tok):
            result.append(tok)
            if len(result) >= n:
                break
    return result


# ─── Sayfa eşleştirme ────────────────────────────────────────

def match_pages(pages_e, pages_q):
    pairs = []
    q_ptr = 0

    for ei in range(len(pages_e)):
        e_tokens = first_meaningful_tokens(pages_e[ei])
        if not e_tokens:
            pairs.append((ei, q_ptr if q_ptr < len(pages_q) else None))
            if q_ptr < len(pages_q):
                q_ptr += 1
            continue

        best_qi = None
        best_score = 0
        for look in range(min(4, len(pages_q) - q_ptr)):
            qi = q_ptr + look
            q_tokens = first_meaningful_tokens(pages_q[qi])
            if not q_tokens:
                continue
            score = 0
            for et, qt in zip(e_tokens, q_tokens):
                if et.lower() == qt.lower():
                    score += 1
                elif len(et) >= 3 and len(qt) >= 3 and et.lower()[:3] == qt.lower()[:3]:
                    score += 0.5
            if score > best_score:
                best_score = score
                best_qi = qi

        if best_qi is not None and best_score >= 0.5:
            for skip_q in range(q_ptr, best_qi):
                pairs.append((None, skip_q))
            pairs.append((ei, best_qi))
            q_ptr = best_qi + 1
        else:
            pairs.append((ei, None))

    while q_ptr < len(pages_q):
        pairs.append((None, q_ptr))
        q_ptr += 1

    return pairs


# ─── Token eşleşme yardımcıları ──────────────────────────────

def tok_eq(a, b):
    """Tam eşleşme (case insensitive)."""
    return a.lower() == b.lower()


def tok_fuzzy(a, b):
    """Gevşek eşleşme: tam eşleşme veya yeterli ortak prefix. İlk harf mutlaka eşit olmalı."""
    al, bl = a.lower(), b.lower()
    if al == bl:
        return True
    if len(al) < 3 or len(bl) < 3:
        return False
    # İlk harf mutlaka eşleşmeli
    if al[0] != bl[0]:
        return False
    # Ortak prefix uzunluğunu bul
    common = 0
    for ca, cb in zip(al, bl):
        if ca == cb:
            common += 1
        else:
            break
    # En az 3 karakter ortak ve kısa olanın %50'si kadar ortak prefix
    ml = min(len(al), len(bl))
    return common >= 3 and common >= ml * 0.5


def concat(toks, start, count):
    """Token'ları birleştir."""
    return "".join(toks[i].lower() for i in range(start, min(start + count, len(toks))))


# ─── Sayfa içi token hizalama ────────────────────────────────

def align_page_tokens(args):
    """
    Tek bir sayfa çiftini hizala.
    
    Algoritma:
      1) İleri yön: elemantr'yi tara, qwen'de eşleşme ara.
         - Tam eşleşme, birleşik token eşleşme, fuzzy eşleşme dene.
         - Eşleşmezse elemantr'yi karşılıksız bırak, qwen pointer'ı KALDIRMA, devam et.
      2) Geri yön: eşleşmemiş elemantr token'larını sondan başa tara.
      3) Kalan eşleşmemişler arasında n-gram eşleme.
      4) Satır oluştur.
    """
    page_idx, e_page, q_page = args

    if not e_page and not q_page:
        return (page_idx, [])
    if not e_page:
        return (page_idx, [("", "", t, l) for t, l in q_page])
    if not q_page:
        return (page_idx, [(t, l, "", "") for t, l in e_page])

    e_toks = [t for t, _ in e_page]
    q_toks = [t for t, _ in q_page]
    e_lems = [l for _, l in e_page]
    q_lems = [l for _, l in q_page]

    ne = len(e_toks)
    nq = len(q_toks)

    e_to_q = [-1] * ne
    q_to_e = [-1] * nq

    # ── İleri yön ──
    qi = 0
    for ei in range(ne):
        if qi >= nq:
            break
        
        # 1) Tam eşleşme
        if tok_eq(e_toks[ei], q_toks[qi]):
            e_to_q[ei] = qi
            q_to_e[qi] = ei
            qi += 1
            continue

        # 2) Qwen fazla bölmüş olabilir: q[qi:qi+k] birleşince e[ei]'ye eşit mi?
        matched = False
        for k in range(2, 5):
            if qi + k - 1 < nq:
                cq = concat(q_toks, qi, k)
                if cq == e_toks[ei].lower():
                    e_to_q[ei] = qi  # ilk qwen parçasına bağla
                    q_to_e[qi] = ei
                    qi += k
                    matched = True
                    break

        if matched:
            continue

        # 3) Elemantr fazla bölmüş olabilir: e[ei:ei+k] birleşince q[qi]'ye eşit mi?
        for k in range(2, 5):
            if ei + k - 1 < ne:
                ce = concat(e_toks, ei, k)
                if ce == q_toks[qi].lower():
                    e_to_q[ei] = qi
                    q_to_e[qi] = ei
                    qi += 1
                    matched = True
                    break

        if matched:
            continue

        # 4) Qwen'de 1-5 adım ileri bak + lookahead teyit
        #    e[ei] ile q[qi+skip] eşleşiyor mu? Eşleşiyorsa,
        #    sonrasında da en az 1 token daha uyuyor mu? ("teyit")
        #    Teyit varsa kesiniz: aradaki qwen token'ları fazlalık.
        def lookahead_confirm(ei_start, qi_start, need=1):
            """ei_start ve qi_start'tan itibaren need kadar ardışık eşleşme var mı?"""
            ok = 0
            ce, cq = ei_start, qi_start
            while ce < ne and cq < nq and ok < need:
                if tok_eq(e_toks[ce], q_toks[cq]) or tok_fuzzy(e_toks[ce], q_toks[cq]):
                    ok += 1
                    ce += 1
                    cq += 1
                else:
                    # qwen birleşik bölmüş olabilir, 2-3 token dene
                    found_concat = False
                    for kk in range(2, 4):
                        if cq + kk - 1 < nq and concat(q_toks, cq, kk) == e_toks[ce].lower():
                            ok += 1
                            ce += 1
                            cq += kk
                            found_concat = True
                            break
                    if not found_concat:
                        break
            return ok >= need

        for skip in range(1, 6):
            if qi + skip >= nq:
                break

            # Tam eşleşme + lookahead
            if tok_eq(e_toks[ei], q_toks[qi + skip]):
                # skip=1 ise 1 teyit yeter, skip büyüdükçe daha fazla teyit iste
                need = min(skip, 2)
                if lookahead_confirm(ei + 1, qi + skip + 1, need):
                    e_to_q[ei] = qi + skip
                    q_to_e[qi + skip] = ei
                    qi = qi + skip + 1
                    matched = True
                    break

            # Birleşik token + skip + lookahead
            for k in range(2, 4):
                if qi + skip + k - 1 < nq:
                    cq = concat(q_toks, qi + skip, k)
                    if cq == e_toks[ei].lower():
                        need = min(skip, 2)
                        if lookahead_confirm(ei + 1, qi + skip + k, need):
                            e_to_q[ei] = qi + skip
                            q_to_e[qi + skip] = ei
                            qi = qi + skip + k
                            matched = True
                            break
            if matched:
                break

            # Fuzzy + skip + lookahead
            if tok_fuzzy(e_toks[ei], q_toks[qi + skip]):
                need = min(skip, 2)
                if lookahead_confirm(ei + 1, qi + skip + 1, need):
                    e_to_q[ei] = qi + skip
                    q_to_e[qi + skip] = ei
                    qi = qi + skip + 1
                    matched = True
                    break

        if matched:
            continue

        # 5) Fuzzy eşleşme (skip olmadan, lookahead teyitsiz — en gevşek)
        if tok_fuzzy(e_toks[ei], q_toks[qi]):
            e_to_q[ei] = qi
            q_to_e[qi] = ei
            qi += 1
            continue

        # 6) Eşleşme bulunamadı — elemantr'yi karşılıksız bırak, qi'yi KALDIRMA
        # (bir sonraki elemantr token'ı aynı qi ile denenecek)

    # ── Geri yön: eşleşmemiş elemantr token'larını sondan dene ──
    # Son eşleşen qi'yi bul
    max_matched_qi = -1
    for ei in range(ne):
        if e_to_q[ei] != -1 and e_to_q[ei] > max_matched_qi:
            max_matched_qi = e_to_q[ei]

    qi_rev = nq - 1
    for ei in range(ne - 1, -1, -1):
        if e_to_q[ei] != -1:
            continue  # zaten eşleşmiş
        if qi_rev <= max_matched_qi:
            break

        # Tam eşleşme
        if tok_eq(e_toks[ei], q_toks[qi_rev]):
            e_to_q[ei] = qi_rev
            q_to_e[qi_rev] = ei
            qi_rev -= 1
            continue

        # Birleşik token (qwen fazla bölmüş)
        matched = False
        for k in range(2, 5):
            if qi_rev - k + 1 >= 0 and qi_rev - k + 1 > max_matched_qi:
                cq = concat(q_toks, qi_rev - k + 1, k)
                if cq == e_toks[ei].lower():
                    e_to_q[ei] = qi_rev - k + 1
                    q_to_e[qi_rev - k + 1] = ei
                    qi_rev -= k
                    matched = True
                    break

        if matched:
            continue

        # Skip geriye
        for skip in range(1, 4):
            if qi_rev - skip > max_matched_qi:
                if tok_eq(e_toks[ei], q_toks[qi_rev - skip]):
                    e_to_q[ei] = qi_rev - skip
                    q_to_e[qi_rev - skip] = ei
                    qi_rev = qi_rev - skip - 1
                    matched = True
                    break

        if matched:
            continue

        # Fuzzy
        if qi_rev > max_matched_qi and tok_fuzzy(e_toks[ei], q_toks[qi_rev]):
            e_to_q[ei] = qi_rev
            q_to_e[qi_rev] = ei
            qi_rev -= 1

    # ── Aşama 3: kalan boşluklar için pozisyon bazlı n-gram ──
    # Eşleşmemiş ardışık blokları bul ve kendi aralarında hizala
    def fill_gap(e_start, e_end, q_start, q_end):
        """Küçük bir boşluğu doldur."""
        gap_e = list(range(e_start, e_end))
        gap_q = list(range(q_start, q_end))
        if not gap_e or not gap_q:
            return

        ge_ptr = 0
        gq_ptr = 0
        while ge_ptr < len(gap_e) and gq_ptr < len(gap_q):
            ei = gap_e[ge_ptr]
            qi = gap_q[gq_ptr]
            if e_to_q[ei] != -1:
                ge_ptr += 1
                continue
            if q_to_e[qi] != -1:
                gq_ptr += 1
                continue

            if tok_eq(e_toks[ei], q_toks[qi]):
                e_to_q[ei] = qi
                q_to_e[qi] = ei
                ge_ptr += 1
                gq_ptr += 1
            elif tok_fuzzy(e_toks[ei], q_toks[qi]):
                e_to_q[ei] = qi
                q_to_e[qi] = ei
                ge_ptr += 1
                gq_ptr += 1
            else:
                # Eşleşmedi — ikisini de atla, karşılıksız kalsınlar
                ge_ptr += 1
                gq_ptr += 1

    # Eşleşmiş çiftleri sıralı al
    matched_pairs = sorted([(ei, e_to_q[ei]) for ei in range(ne) if e_to_q[ei] != -1],
                           key=lambda x: x[0])

    # Boşlukları doldur
    prev_ei, prev_qi = -1, -1
    for ei, qi in matched_pairs:
        if ei > prev_ei + 1 or qi > prev_qi + 1:
            fill_gap(prev_ei + 1, ei, prev_qi + 1, qi)
        prev_ei, prev_qi = ei, qi
    # Son boşluk
    fill_gap(prev_ei + 1, ne, prev_qi + 1, nq)

    # ── Satır oluşturma ──
    rows = []
    q_emitted = set()

    prev_qi = -1
    for ei in range(ne):
        qi = e_to_q[ei]
        if qi != -1:
            # Aradaki karşılıksız qwen token'ları
            for gap_qi in range(prev_qi + 1, qi):
                if gap_qi not in q_emitted and q_to_e[gap_qi] == -1:
                    rows.append(("", "", q_toks[gap_qi], q_lems[gap_qi]))
                    q_emitted.add(gap_qi)
            rows.append((e_toks[ei], e_lems[ei], q_toks[qi], q_lems[qi]))
            q_emitted.add(qi)
            prev_qi = qi
        else:
            rows.append((e_toks[ei], e_lems[ei], "", ""))

    # Sondaki karşılıksız qwen token'ları
    for qi in range(nq):
        if qi not in q_emitted and q_to_e[qi] == -1:
            rows.append(("", "", q_toks[qi], q_lems[qi]))

    return (page_idx, rows)


# ─── Ana akış ────────────────────────────────────────────────

def main():
    elemantr_file = "elemantr_sonuc.txt"
    qwen_file = "qwen_sonuc.txt"
    output_file = "birlesik.tsv"

    t0 = time.time()
    workers = max(1, cpu_count() - 1)

    print(f"Okunuyor: {elemantr_file}")
    entries_e = parse_file(elemantr_file)
    print(f"  -> {len(entries_e)} entry")

    print(f"Okunuyor: {qwen_file}")
    entries_q = parse_file(qwen_file)
    print(f"  -> {len(entries_q)} entry")

    # 1) Sayfalara böl
    print("Sayfalara bölünüyor...")
    pages_e = split_pages(entries_e)
    pages_q = split_pages(entries_q)
    print(f"  Elemantr: {len(pages_e)} sayfa")
    print(f"  Qwen: {len(pages_q)} sayfa")

    # 2) Sayfaları eşleştir
    print("Sayfalar eşleştiriliyor...")
    page_pairs = match_pages(pages_e, pages_q)

    matched_pages = sum(1 for ei, qi in page_pairs if ei is not None and qi is not None)
    only_e_p = sum(1 for ei, qi in page_pairs if ei is not None and qi is None)
    only_q_p = sum(1 for ei, qi in page_pairs if ei is None and qi is not None)
    print(f"  Eşleşen sayfa: {matched_pages}")
    if only_e_p:
        print(f"  Karşılıksız elemantr: {only_e_p}")
    if only_q_p:
        print(f"  Karşılıksız qwen: {only_q_p}")

    # 3) Görevleri hazırla
    tasks = []
    for idx, (ei, qi) in enumerate(page_pairs):
        if ei is not None and qi is not None:
            tasks.append((idx, pages_e[ei], pages_q[qi]))
        elif ei is not None:
            tasks.append((idx, pages_e[ei], []))
        else:
            tasks.append((idx, [], pages_q[qi]))

    # 4) Paralel hizalama
    print(f"Sayfa içi hizalama ({workers} worker)...")
    results = {}
    with Pool(processes=workers) as pool:
        for page_idx, rows in tqdm(
            pool.imap_unordered(align_page_tokens, tasks),
            total=len(tasks),
            desc="Hizalama",
            unit="sayfa",
            ncols=80,
        ):
            results[page_idx] = rows

    # 5) Sıralı birleştirme
    all_rows = []
    for idx in range(len(page_pairs)):
        if idx in results:
            all_rows.extend(results[idx])

    # 6) Yaz
    print(f"Yazılıyor: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("elemantr_token\telemantr_lemma\tqwen_token\tqwen_lemma\n")
        for row in all_rows:
            f.write("\t".join(row) + "\n")

    elapsed = time.time() - t0
    both = sum(1 for r in all_rows if r[0] and r[2])
    only_e = sum(1 for r in all_rows if r[0] and not r[2])
    only_q = sum(1 for r in all_rows if not r[0] and r[2])

    print(f"\n{'='*50}")
    print(f"Tamamlandı! {elapsed:.1f} saniye")
    print(f"  Toplam satır  : {len(all_rows)}")
    print(f"  Eşleşen       : {both}")
    print(f"  Sadece elemantr: {only_e}")
    print(f"  Sadece qwen   : {only_q}")


if __name__ == "__main__":
    main()