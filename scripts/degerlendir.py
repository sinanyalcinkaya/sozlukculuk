#!/usr/bin/env python3
"""
Elemantr vs Qwen lemmatizasyon değerlendirmesi.
birlesik.tsv dosyasını okuyup her satırı etiketler, istatistik üretir.

Kullanım: python degerlendir.py
Girdi: birlesik.tsv (aynı dizinde)
Çıktı: degerlendirme.tsv  — her satır etiketli
       rapor.txt          — özet istatistikler
"""

import os
import sys


# ─── Yardımcılar ─────────────────────────────────────────────

PUNCT_CHARS = set('.,!?;:"\'-|()[]{}…–—«»/\\0123456789')


def is_punct(token):
    """Token sadece noktalama/rakam mı?"""
    return bool(token) and all(c in PUNCT_CHARS for c in token)


def clean_lemma(lemma):
    """Lemma'yı karşılaştırma için temizle: * sil, küçük harf, strip."""
    return lemma.rstrip("*").lower().strip()


def has_star(lemma):
    """Elemantr lemma'sı * ile bitiyor mu?"""
    return lemma.endswith("*")


# ─── Etiketleme ──────────────────────────────────────────────

def label_row(et, el, qt, ql):
    """
    Bir satırı etiketle.

    Etiketler:
      noktalama        — Token noktalama işareti, değerlendirme dışı
      bos_e            — Sadece qwen'de var (elemantr boş), token bölünme farkı
      bos_q            — Sadece elemantr'de var (qwen boş), token bölünme farkı
      ayni             — İki lemma aynı (kesin doğru, token/yıldız farkı önemsiz)
      farkli           — İki lemma farklı, yıldızsız (biri yanlış)
      farkli_belirsiz  — İki lemma farklı, elemantr yıldızlı (hangisi doğru belirsiz)
      token_farkli_x   — Token'lar farklı eşleşmiş, lemma da farklı (güvenilmez)
    """
    e_var = bool(et.strip())
    q_var = bool(qt.strip())

    # Boş durumları
    if not e_var and not q_var:
        return "bos"
    if not e_var:
        return "bos_e"
    if not q_var:
        return "bos_q"

    # Noktalama
    if is_punct(et) or is_punct(qt):
        return "noktalama"

    el_clean = clean_lemma(el)
    ql_clean = clean_lemma(ql)
    star = has_star(el)

    # Lemmalar aynıysa → token veya yıldız farkı önemsiz, kesin doğru
    if el_clean == ql_clean:
        return "ayni"

    # Lemmalar farklı
    tokens_same = (et.lower() == qt.lower())
    if tokens_same:
        return "farkli_belirsiz" if star else "farkli"
    else:
        return "token_farkli_x"


# ─── Ana akış ────────────────────────────────────────────────

def main():
    input_file = "birlesik.tsv"
    output_file = "degerlendirme.tsv"
    report_file = "rapor.txt"

    if not os.path.exists(input_file):
        print(f"HATA: {input_file} bulunamadı!")
        sys.exit(1)

    # Sayaçlar
    counts = {}
    total = 0

    # Oku ve etiketle
    print(f"Okunuyor: {input_file}")
    rows = []
    with open(input_file, "r", encoding="utf-8") as f:
        header = next(f).rstrip("\n")
        for line in f:
            parts = line.rstrip("\n").split("\t")
            while len(parts) < 4:
                parts.append("")
            et, el, qt, ql = parts[0], parts[1], parts[2], parts[3]

            label = label_row(et, el, qt, ql)
            rows.append((et, el, qt, ql, label))

            counts[label] = counts.get(label, 0) + 1
            total += 1

    # Etiketli dosya yaz
    print(f"Yazılıyor: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("elemantr_token\telemantr_lemma\tqwen_token\tqwen_lemma\tetiket\n")
        for row in rows:
            f.write("\t".join(row) + "\n")

    # ─── Rapor ──────────────────────────────────────────
    disi_birakilan = counts.get("noktalama", 0) + counts.get("bos", 0)
    bos_e = counts.get("bos_e", 0)
    bos_q = counts.get("bos_q", 0)
    ayni = counts.get("ayni", 0)
    farkli = counts.get("farkli", 0)
    farkli_belirsiz = counts.get("farkli_belirsiz", 0)
    token_farkli_x = counts.get("token_farkli_x", 0)

    # Değerlendirilebilir: lemmalar karşılaştırılabilen tüm satırlar
    degerlendirilir = ayni + farkli + farkli_belirsiz + token_farkli_x

    report_lines = []
    def pr(s=""):
        report_lines.append(s)
        print(s)

    pr("=" * 60)
    pr("LEMMATIZASYON DEĞERLENDİRME RAPORU")
    pr("Elemantr (master) vs Qwen:30b (slave)")
    pr("=" * 60)
    pr()
    pr(f"Toplam satır: {total:,}")
    pr()
    pr("─── GENEL DAĞILIM ───")
    pr(f"  Noktalama / boş (değerlendirme dışı)  : {disi_birakilan:>8,}")
    pr(f"  Tokenizasyon farkı (tek taraf boş)     : {bos_e + bos_q:>8,}")
    pr(f"    Sadece qwen'de var (bos_e)            : {bos_e:>8,}")
    pr(f"    Sadece elemantr'de var (bos_q)        : {bos_q:>8,}")
    pr(f"  Değerlendirilebilir                    : {degerlendirilir:>8,}")
    pr()

    pr("─── LEMMA UYUMU ───")
    pr()
    pr(f"  Aynı (iki model uyuşuyor)              : {ayni:>8,}  ({ayni/degerlendirilir*100:.1f}%)")
    pr(f"  Farklı (kesin, yıldızsız)              : {farkli:>8,}  ({farkli/degerlendirilir*100:.1f}%)")
    pr(f"  Farklı (belirsiz, elemantr yıldızlı)   : {farkli_belirsiz:>8,}  ({farkli_belirsiz/degerlendirilir*100:.1f}%)")
    pr(f"  Token farklı + lemma farklı (güvenilmez): {token_farkli_x:>8,}  ({token_farkli_x/degerlendirilir*100:.1f}%)")
    pr()

    farkli_toplam = farkli + farkli_belirsiz + token_farkli_x
    pr("─── ÖZET UYUM ORANLARI ───")
    pr()
    pr(f"  Uyum oranı (ayni / değerlendirilebilir):")
    pr(f"    {ayni:,} / {degerlendirilir:,} = {ayni/degerlendirilir*100:.1f}%")
    pr()
    pr(f"  Uyumsuzluk (toplam farklı):")
    pr(f"    {farkli_toplam:,} / {degerlendirilir:,} = {farkli_toplam/degerlendirilir*100:.1f}%")
    pr()

    # Yıldızsız kesin sonuçlar ayrı
    kesin = ayni + farkli  # yıldızsız + aynı token olanlar
    # ayni içinde yıldızlı olanlar da var artık, onları sayalım
    # Aslında ayni hepsini kapsıyor. Kesin alt küme için:
    # ayni'dan yıldızlıları çıkaramayız çünkü label'da ayrım yok.
    # Ama farkli kesin yıldızsız, farkli_belirsiz yıldızlı.
    pr(f"  Kesin uyumsuzluk (farkli, yıldızsız)   : {farkli:>8,}")
    pr(f"  Belirsiz uyumsuzluk (farkli_belirsiz)  : {farkli_belirsiz:>8,}")
    pr()

    pr("─── ETİKET DETAY ───")
    for label in ["ayni", "farkli", "farkli_belirsiz",
                   "token_farkli_x", "bos_e", "bos_q",
                   "noktalama", "bos"]:
        c = counts.get(label, 0)
        if c > 0:
            pr(f"  {label:<22s}: {c:>8,}  ({c/total*100:.1f}%)")
    pr()
    pr("=" * 60)
    pr()
    pr("Etiket açıklamaları:")
    pr("  ayni             = İki lemma aynı (kesin doğru, token/yıldız farkı önemsiz)")
    pr("  farkli           = Aynı token, farklı lemma, yıldızsız (kesin uyumsuzluk)")
    pr("  farkli_belirsiz  = Aynı token, farklı lemma, elemantr yıldızlı")
    pr("  token_farkli_x   = Token farklı eşleşmiş, lemma farklı (güvenilmez)")
    pr("  bos_e            = Sadece qwen'de var (tokenizasyon farkı)")
    pr("  bos_q            = Sadece elemantr'de var (tokenizasyon farkı)")
    pr("  noktalama        = Noktalama işareti (değerlendirme dışı)")

    # Rapor dosyası yaz
    print(f"\nYazılıyor: {report_file}")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print("Tamamlandı!")


if __name__ == "__main__":
    main()