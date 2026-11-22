# -*- coding: utf-8 -*-
"""
GTA 6 Viral Video Turkcelestirici (YouTube Shorts + TikTok + Instagram Reels)
En cok izlenen / begenilen yabanci GTA 6 kisa videolarini bulur, ayni videonun
farkli hesaplardaki kopyalarini tek videoda birlestirir (kaynak = ilk yukleyen),
konusmayi yaziya doker, Turkceye cevirir ve Turkce altyazili 1080x1920 mp4 yapar.

Kaynaklar:
  youtube   : YouTube aramasi (izlenmeye gore, secilen donem)
  instagram : #hashtag sayfasi (tarayicida Instagram'a giris yapilmis olmali,
              --tarayici firefox/edge/chrome ile cerezler alinir)
  hesaplar  : hesaplar.txt icindeki TikTok / YouTube / Instagram hesaplarinin son videolari
  --link    : tek bir video linki (YouTube, TikTok, Instagram fark etmez)

Adimlar:
 1. Topla: her kaynaktan adaylar + izlenme/begeni/tarih
 2. Kopyalari birlestir: ayni sure + benzer kapak resmi / baslik = ayni video
 3. Indir + Whisper ile kelime kelime yaziya dok
    (daha once yapilan bir videonun yeniden yuklemesiyse konusmadan anlar, atlar)
 4. Turkceye cevir (Google -> MyMemory -> Claude)
 5. Altyazili dikey video + aciklama.txt (orijinal hesaba kaynak verilerek)
"""
import argparse
import base64
import difflib
import json
import re
import shutil
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import klipci
from klipci import log, guvenli_ad, tr_upper

CIKTI = klipci.CIKTI / "shorts"
ISLENENLER = CIKTI / "islenenler.txt"
METINLER = CIKTI / "yapilan_metinler.json"
HESAPLAR = klipci.KOK / "hesaplar.txt"

DONEMLER = {"gun": (2, 1), "hafta": (3, 7), "ay": (4, 31), "yil": (5, 366), "hepsi": (None, None)}
TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
PLATFORM_AD = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram"}

TARAYICI = None   # --tarayici ile dolar: yt-dlp cerezleri buradan alir


def ydl(**kw):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noprogress": True}
    if TARAYICI:
        opts["cookiesfrombrowser"] = (TARAYICI,)
    opts.update(kw)
    return yt_dlp.YoutubeDL(opts)


# ---------------------------------------------------------------- 1. toplama
def _varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def arama_param(donem):
    """YouTube 'sp' parametresi: izlenmeye gore sirala + kisa video (<4 dk) + donem."""
    ic = b""
    kod = DONEMLER[donem][0]
    if kod:
        ic += b"\x08" + _varint(kod)          # yukleme tarihi
    ic += b"\x18\x01"                         # sure: 4 dakikadan kisa
    sp = b"\x08\x03" + b"\x12" + _varint(len(ic)) + ic   # siralama: izlenme
    return base64.b64encode(sp).decode()


def liste_linkleri(url, limit):
    """Arama / hashtag / hesap sayfasindaki video linklerini dondurur (detaysiz, hizli)."""
    with ydl(skip_download=True, extract_flat="in_playlist", playlistend=limit) as y:
        info = y.extract_info(url, download=False)
    out = []
    for e in info.get("entries") or []:
        u = e.get("url") or e.get("webpage_url")
        if not u and e.get("id"):
            u = f"https://www.youtube.com/shorts/{e['id']}"
        if u and u not in out:
            out.append(u)
    return out


def youtube_ara(sorgu, donem, limit):
    url = ("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(sorgu) +
           "&sp=" + urllib.parse.quote(arama_param(donem)))
    return liste_linkleri(url, limit)


def instagram_tag(etiket, limit):
    return liste_linkleri(f"https://www.instagram.com/explore/tags/{etiket}/", limit)


def hesaplar_oku():
    if not HESAPLAR.exists():
        return []
    out = []
    for s in HESAPLAR.read_text(encoding="utf-8").splitlines():
        s = s.strip()
        if s.startswith("#"):
            continue
        s = s.split(" #", 1)[0].split()[0] if s else ""
        if not s:
            continue
        if s.startswith("@"):                       # @kullanici -> TikTok
            s = f"https://www.tiktok.com/{s}"
        out.append(s)
    return out


def detay_al(url):
    with ydl(skip_download=True, noplaylist=True) as y:
        return y.extract_info(url, download=False)


def platform(info):
    k = (info.get("extractor_key") or info.get("extractor") or "").lower()
    for p in PLATFORM_AD:
        if k.startswith(p):
            return p
    return k or "video"


def gun_once(upload_date, ts=None):
    try:
        if ts:
            d = datetime.fromtimestamp(ts, timezone.utc)
        else:
            d = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        return max(1.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400)
    except Exception:
        return None


def turkce_mi(info):
    metin = f"{info.get('title') or ''} {(info.get('description') or '')[:300]}"
    dil = (info.get("language") or "").lower()
    return dil.startswith("tr") or len(TR_HARF.findall(metin)) >= 3


def aday_yap(info):
    p = platform(info)
    izl = info.get("view_count") or 0
    beg = info.get("like_count") or 0
    gun = gun_once(info.get("upload_date") or "", info.get("timestamp"))
    baslik = info.get("title") or ""
    if p == "instagram" or baslik.lower().startswith("video by"):
        baslik = (info.get("description") or baslik).split("\n")[0][:120]
    kanal = (info.get("uploader") or info.get("channel") or info.get("uploader_id") or "")
    return {
        "anahtar": f"{p}:{info.get('id')}", "id": info.get("id"), "platform": p,
        "baslik": baslik, "kanal": kanal,
        "kanal_url": info.get("channel_url") or info.get("uploader_url") or "",
        "url": info.get("webpage_url") or info.get("original_url") or "",
        "izlenme": izl, "begeni": beg, "sure": info.get("duration") or 0, "gun": gun,
        "tarih": info.get("timestamp") or 0, "upload_date": info.get("upload_date") or "",
        "hiz": round(izl / gun) if gun else 0,
        "kapak": info.get("thumbnail") or "",
    }


def islenenler():
    if ISLENENLER.exists():
        return set(ISLENENLER.read_text(encoding="utf-8").split())
    return set()


def islendi_isaretle(ad):
    CIKTI.mkdir(parents=True, exist_ok=True)
    with ISLENENLER.open("a", encoding="utf-8") as f:
        for k in [ad["anahtar"]] + [x["anahtar"] for x in ad.get("kopyalar", [])]:
            f.write(k + "\n")


def kaynaklardan_topla(a):
    linkler = []   # (kaynak_adi, url)
    kaynaklar = [k.strip() for k in a.kaynak.split(",") if k.strip()]
    if "youtube" in kaynaklar:
        log(f"    YouTube aranıyor: \"{a.ara}\"...")
        try:
            linkler += [("youtube", u) for u in youtube_ara(a.ara, a.donem, a.tara)]
        except Exception as e:
            log(f"    YouTube araması olmadı ({type(e).__name__}: {str(e)[:120]})")
    if "instagram" in kaynaklar:
        etiket = a.etiket or re.sub(r"\W+", "", a.ara.lower())
        log(f"    Instagram #{etiket} taranıyor...")
        try:
            linkler += [("instagram", u) for u in instagram_tag(etiket, a.tara)]
        except Exception as e:
            log(f"    Instagram olmadı ({type(e).__name__}). Instagram giriş istiyor: tarayıcıda "
                f"instagram.com'a giriş yap ve --tarayici firefox (ya da edge/chrome) ekle.")
    if "hesaplar" in kaynaklar:
        hes = hesaplar_oku()
        if hes:
            log(f"    hesaplar.txt: {len(hes)} hesabın son videoları alınıyor...")
        for h in hes:
            try:
                linkler += [("hesap", u) for u in liste_linkleri(h, a.hesap_son)]
            except Exception as e:
                print(f"    {h}: alınamadı ({type(e).__name__})", flush=True)
    return linkler


def adaylari_topla(a):
    log("1/5 Videolar toplanıyor...")
    linkler = kaynaklardan_topla(a)
    log(f"    {len(linkler)} video bulundu, ayrıntılar alınıyor...")
    atla = islenenler() if not a.tekrar else set()
    max_gun = DONEMLER[a.donem][1]
    adaylar, gorulen = [], set()
    for i, (_, url) in enumerate(linkler, 1):
        if i % 10 == 0:
            print(f"    {i}/{len(linkler)} incelendi, {len(adaylar)} uygun", flush=True)
        try:
            info = detay_al(url)
        except Exception as e:
            print(f"    {url[:60]}: alınamadı ({type(e).__name__})", flush=True)
            continue
        if info.get("_type") == "playlist":
            continue
        ad = aday_yap(info)
        if ad["anahtar"] in gorulen or ad["anahtar"] in atla or ad["id"] in atla:
            continue
        gorulen.add(ad["anahtar"])
        if not ad["sure"] or ad["sure"] > a.max_sure or turkce_mi(info):
            continue
        if max_gun and ad["gun"] and ad["gun"] > max_gun:
            continue
        if ad["izlenme"] < a.min_izlenme and ad["begeni"] * 30 < a.min_izlenme:
            continue
        adaylar.append(ad)
    return adaylar


# ---------------------------------------------------------------- 2. kopyalar
def kapak_izi(url):
    """Kapak resminin 64 bitlik fark-hash'i (dHash). Olmazsa None."""
    if not url:
        return None
    try:
        import cv2
        import numpy as np
        import requests
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        # repostlarda eklenen siyah bantlari kirp
        satir = np.flatnonzero((img > 25).mean(axis=1) > 0.1)
        sutun = np.flatnonzero((img > 25).mean(axis=0) > 0.1)
        if len(satir) > 10 and len(sutun) > 10:
            img = img[satir[0]:satir[-1] + 1, sutun[0]:sutun[-1] + 1]
        # ustune yazi yazilan kenarlari at: ortadaki %70
        h, w = img.shape
        img = img[int(h * .15):int(h * .85), int(w * .15):int(w * .85)]
        k = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
        bit = (k[:, 1:] > k[:, :-1]).flatten()
        return int("".join("1" if b else "0" for b in bit), 2)
    except Exception:
        return None


def benzer_baslik(x, y):
    x = re.sub(r"[#@]\w+|\W+", " ", x.lower()).split()
    y = re.sub(r"[#@]\w+|\W+", " ", y.lower()).split()
    if len(x) < 3 or len(y) < 3:
        return False
    return difflib.SequenceMatcher(None, x, y).ratio() >= 0.8


def kopyalari_birlestir(adaylar):
    """Ayni videonun farkli hesaplardaki yuklemelerini tek gruba toplar.
    Grup temsilcisi = ilk yukleyen (orijinal), siralama = toplam izlenme."""
    n = len(adaylar)
    if n < 2:
        for ad in adaylar:
            ad["kopyalar"], ad["toplam_izlenme"], ad["toplam_begeni"] = [], ad["izlenme"], ad["begeni"]
        return adaylar
    log(f"2/5 {n} video arasında kopyalar aranıyor (herkes birbirinden alıyor)...")
    for ad in adaylar:
        ad["_iz"] = kapak_izi(ad.get("kapak"))
    ata = list(range(n))

    def bul(i):
        while ata[i] != i:
            ata[i] = ata[ata[i]]
            i = ata[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            x, y = adaylar[i], adaylar[j]
            if abs(x["sure"] - y["sure"]) > 1.6:
                continue
            ayni = benzer_baslik(x["baslik"], y["baslik"])
            if not ayni and x["_iz"] is not None and y["_iz"] is not None:
                ayni = bin(x["_iz"] ^ y["_iz"]).count("1") <= 10
            if ayni:
                ata[bul(i)] = bul(j)
    gruplar = {}
    for i, ad in enumerate(adaylar):
        gruplar.setdefault(bul(i), []).append(ad)
    out = []
    for g in gruplar.values():
        g.sort(key=lambda x: (x["tarih"] or 9e12, x["upload_date"] or "99999999"))
        orj = dict(g[0])
        orj["kopyalar"] = [{k: x[k] for k in ("anahtar", "platform", "kanal", "url", "izlenme",
                                                 "begeni")} for x in g[1:]]
        orj["toplam_izlenme"] = sum(x["izlenme"] for x in g)
        orj["toplam_begeni"] = sum(x["begeni"] for x in g)
        out.append(orj)
    for ad in out + adaylar:
        ad.pop("_iz", None)
    kop = sum(len(x["kopyalar"]) for x in out)
    if kop:
        log(f"    {kop} kopya bulundu, {len(out)} farklı video kaldı")
    return out


def sirala(adaylar, nasil):
    def puan(x):
        izl = x["toplam_izlenme"] or x["toplam_begeni"] * 30   # Instagram izlenme vermeyebilir
        if nasil == "begeni":
            return (x["toplam_begeni"], izl)
        if nasil == "hiz":
            return (izl / (x["gun"] or 1), izl)
        return (izl, x["toplam_begeni"])
    adaylar.sort(key=puan, reverse=True)
    return adaylar


def sayi(n):
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}B"
    return str(n)


# ---------------------------------------------------------------- 3. indirme
def video_indir(url, hedef: Path):
    with ydl(format="bv*[height<=1920]+ba/b[height<=1920]/b",
             outtmpl=str(hedef.with_suffix(".%(ext)s")), ffmpeg_location=klipci.FFMPEG,
             merge_output_format="mp4", noplaylist=True) as y:
        y.download([url])
    for f in hedef.parent.glob(hedef.stem + ".*"):
        if f.suffix in (".mp4", ".mkv", ".webm", ".mov"):
            return f
    raise RuntimeError("Video indirilemedi")


def video_boyut(video: Path):
    import cv2
    cap = cv2.VideoCapture(str(video))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return W, H


def yapilan_metinler():
    if METINLER.exists():
        try:
            return json.loads(METINLER.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def daha_once_yapildi(metin):
    """Konusma metni daha once yapilan bir videoyla ayniysa onun anahtarini dondurur."""
    k = metin.lower().split()
    if len(k) < 6:
        return None
    for anahtar, eski in yapilan_metinler().items():
        e = (eski["metin"] if isinstance(eski, dict) else eski).lower().split()
        if len(e) >= 6 and difflib.SequenceMatcher(None, k, e).ratio() >= 0.75:
            return anahtar
    return None


def metin_kaydet(anahtar, metin, klasor):
    d = yapilan_metinler()
    d[anahtar] = {"metin": metin, "klasor": str(klasor)}
    METINLER.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")


def orijinali_duzelt(eski_anahtar, ad):
    """Atlanan kopya, daha once yapilan videodan ONCE yuklenmisse asil orijinal odur:
    hazir videonun aciklamasini ona kaynak verecek sekilde yeniden yaz."""
    kayit = yapilan_metinler().get(eski_anahtar)
    if not isinstance(kayit, dict):
        return
    kd = Path(kayit["klasor"])
    bj = kd / "bilgi.json"
    if not bj.exists():
        return
    try:
        b = json.loads(bj.read_text(encoding="utf-8"))
        eski_t, yeni_t = b.get("tarih") or 9e12, ad.get("tarih") or 9e12
        if yeni_t >= eski_t and not (yeni_t == eski_t == 9e12 and
                                     (ad.get("upload_date") or "9") < (b.get("upload_date") or "9")):
            # yeni bulunan daha sonra yuklenmis: sadece kopya olarak ekle
            b.setdefault("kopyalar", []).append({k: ad[k] for k in
                                                 ("anahtar", "platform", "kanal", "url",
                                                  "izlenme", "begeni")})
        else:
            onceki = {k: b[k] for k in ("anahtar", "platform", "kanal", "url", "izlenme", "begeni")}
            for k in ("anahtar", "id", "platform", "baslik", "kanal", "kanal_url", "url",
                      "izlenme", "begeni", "tarih", "upload_date"):
                b[k] = ad.get(k)
            b["kopyalar"] = [onceki] + b.get("kopyalar", []) + ad.get("kopyalar", [])
            log(f"    Asıl orijinal bu ({ad['kanal']}): hazır videonun kaynağı düzeltildi")
        b["toplam_izlenme"] = b.get("toplam_izlenme", 0) + ad.get("toplam_izlenme", 0)
        b["toplam_begeni"] = b.get("toplam_begeni", 0) + ad.get("toplam_begeni", 0)
        bj.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
        (kd / "aciklama.txt").write_text(aciklama_yaz(b, b.get("baslik_tr"), b.get("altyazi")),
                                         encoding="utf-8")
    except Exception as e:
        log(f"    (kaynak düzeltilemedi: {type(e).__name__})")


# ---------------------------------------------------------------- 5. aciklama
def aciklama_yaz(ad, baslik_tr, tr_parcalar):
    tr = baslik_tr
    if not tr and tr_parcalar:
        tr = max((p.get("tr", "") for p in tr_parcalar), key=len)[:70]
    tr = tr_upper((tr or ad["baslik"])[:90])
    tik = "#gta6 #gta6türkiye #gta6klip #gta #oyun #keşfet #fyp"
    ig = "#gta6 #gta6türkiye #gta6klip #reels #oyun #keşfet"
    yt = "#gta6 #gta6türkiye #shorts"
    plat = PLATFORM_AD.get(ad["platform"], ad["platform"])
    kaynak = f"Kaynak: {ad['kanal']} ({plat}) {ad['url']}"
    kop = "".join(f"  - {PLATFORM_AD.get(k['platform'], k['platform'])} {k['kanal']}: "
                  f"{sayi(k['izlenme'])} izl | {k['url']}\n" for k in ad.get("kopyalar", []))
    return (f"=== TIKTOK ===\n{tr} 😳 {tik}\n{kaynak}\n\n"
            f"=== INSTAGRAM REELS ===\n{tr} 😳\n\nOrijinal video: @{ad['kanal']} ({plat})\n"
            f"Türkçe altyazı bizden.\n{ig}\n\n"
            f"=== YOUTUBE SHORTS ===\nBaslik (max 100 karakter):\n{tr[:85]} #shorts\n\n"
            f"Aciklama:\n{tr}\nTürkçe altyazı: biz. Orijinal video: {ad['kanal']} ({plat})\n"
            f"{ad['url']}\n{yt}\n\n"
            f"=== NOT ===\nOrijinal baslik: {ad['baslik']}\n"
            f"Orijinal ({plat}): {sayi(ad['izlenme'])} izlenme, {sayi(ad['begeni'])} begeni\n"
            f"Tum kopyalarla toplam: {sayi(ad['toplam_izlenme'])} izlenme, "
            f"{sayi(ad['toplam_begeni'])} begeni\n"
            + (f"Ayni videoyu yukleyen diger hesaplar:\n{kop}" if kop else ""))


# ---------------------------------------------------------------- ana akis
def isle(ad, a, sira):
    kd = CIKTI / guvenli_ad(f"{sira}_{ad['platform']}_{ad['kanal']}_{ad['id']}", 70)
    kd.mkdir(parents=True, exist_ok=True)
    plat = PLATFORM_AD.get(ad["platform"], ad["platform"])
    log(f"3/5 İndiriliyor ({plat}): {ad['baslik'][:55]} ({sayi(ad['toplam_izlenme'])} izlenme, "
        f"{len(ad.get('kopyalar', []))} kopya)")
    kaynak = video_indir(ad["url"], kd / "kaynak")
    wav = kd / "_ses.wav"
    klipci.calistir([klipci.FFMPEG, "-y", "-v", "error", "-i", str(kaynak), "-ac", "1",
                     "-ar", "16000", str(wav)])
    try:
        seg, dil = klipci.yaziya_dok(wav, a.model, kelime=True)
    finally:
        wav.unlink(missing_ok=True)
    kelimeler = [w for s in seg for w in s.get("kelimeler", [])]
    metin = " ".join(w["k"] for w in kelimeler)
    neden = None
    if dil == "tr":
        neden = "video zaten Türkçe"
    elif len(kelimeler) < a.min_kelime:
        neden = f"konuşma yok/çok az ({len(kelimeler)} kelime)"
    elif not a.tekrar:
        eski = daha_once_yapildi(metin)
        if eski:
            neden = f"bu video daha önce yapıldı ({eski}), aynı videonun başka yüklemesi"
            orijinali_duzelt(eski, ad)
    if neden:
        log(f"    Atlanıyor: {neden}")
        shutil.rmtree(kd, ignore_errors=True)
        return False
    log(f"4/5 {len(kelimeler)} kelime ({dil}), Türkçeye çevriliyor...")
    tr_parcalar = klipci.cumleler(kelimeler)
    ceviri = klipci.cevir_tr([p["en"] for p in tr_parcalar] + [ad["baslik"] or "..."], kaynak=dil)
    baslik_tr = None
    if ceviri and len(ceviri) == len(tr_parcalar) + 1:
        baslik_tr = ceviri[-1]
        for p, t in zip(tr_parcalar, ceviri[:-1]):
            p["tr"] = t
    else:
        tr_parcalar = None
        log("    Çeviri olmadı, orijinal dilde altyazı yapılıyor")
    mod = a.altyazi if tr_parcalar else "en"
    W, H = video_boyut(kaynak)
    log(f"5/5 Altyazılı video yapılıyor ({W}x{H} -> 1080x1920)...")
    cikis = kd / f"video{sira}_{guvenli_ad(ad['kanal'], 20)}_tr.mp4"
    klipci.klip_render(kaynak, cikis, kelimeler, (None, W, H), mod, tr_parcalar)
    (kd / "aciklama.txt").write_text(aciklama_yaz(ad, baslik_tr, tr_parcalar), encoding="utf-8")
    (kd / "bilgi.json").write_text(json.dumps({**ad, "dil": dil, "baslik_tr": baslik_tr,
                                               "altyazi": tr_parcalar}, ensure_ascii=False,
                                              indent=1), encoding="utf-8")
    metin_kaydet(ad["anahtar"], metin, kd)
    kaynak.unlink(missing_ok=True)
    log(f"    HAZIR: {cikis}")
    return True


def main():
    global TARAYICI
    ap = argparse.ArgumentParser(description="Viral GTA 6 videolarını Türkçe altyazılı yap")
    ap.add_argument("--kaynak", default="youtube,instagram,hesaplar",
                    help="youtube, instagram, hesaplar (virgülle). Varsayılan hepsi")
    ap.add_argument("--ara", default="GTA 6", help='YouTube arama kelimesi (varsayılan "GTA 6")')
    ap.add_argument("--etiket", default="", help="Instagram hashtag (varsayılan: gta6)")
    ap.add_argument("--tarayici", default="",
                    help="Instagram/TikTok girişi için çerezleri bu tarayıcıdan al: "
                         "firefox, edge, chrome")
    ap.add_argument("--kac", type=int, default=3, help="Kaç video yapılsın (varsayılan 3)")
    ap.add_argument("--donem", default="hafta", choices=list(DONEMLER),
                    help="gun/hafta/ay/yil/hepsi (varsayılan hafta)")
    ap.add_argument("--sirala", default="izlenme", choices=["izlenme", "begeni", "hiz"],
                    help="izlenme (varsayılan), begeni, hiz = günlük izlenme")
    ap.add_argument("--tara", type=int, default=40, help="Her kaynaktan kaç sonuç incelensin")
    ap.add_argument("--hesap-son", type=int, default=12,
                    help="hesaplar.txt'deki her hesabın son kaç videosuna bakılsın")
    ap.add_argument("--max-sure", type=int, default=180, help="En uzun video (sn)")
    ap.add_argument("--min-izlenme", type=int, default=10000)
    ap.add_argument("--min-kelime", type=int, default=6,
                    help="Bundan az konuşma varsa (sadece müzik) atla")
    ap.add_argument("--model", default="small", help="Whisper modeli: tiny/base/small/medium")
    ap.add_argument("--altyazi", default="tr", choices=["tr", "ikili", "en"],
                    help="tr: sadece Türkçe (varsayılan), ikili: orijinal + Türkçe")
    ap.add_argument("--link", help="Aramak yerine bu videoyu Türkçeleştir (YouTube/TikTok/Instagram)")
    ap.add_argument("--tekrar", action="store_true",
                    help="Daha önce yapılan videoları da tekrar değerlendir")
    ap.add_argument("--sadece-liste", action="store_true",
                    help="Video yapma, sadece en viral adayları listele")
    a = ap.parse_args()

    TARAYICI = a.tarayici.strip().lower() or None
    klipci.FFMPEG = klipci.ffmpeg_yolu()
    CIKTI.mkdir(parents=True, exist_ok=True)

    if a.link:
        ad = aday_yap(detay_al(a.link.strip()))
        ad.update(kopyalar=[], toplam_izlenme=ad["izlenme"], toplam_begeni=ad["begeni"])
        adaylar = [ad]
        a.kac, a.tekrar = 1, True
    else:
        adaylar = sirala(kopyalari_birlestir(adaylari_topla(a)), a.sirala)
        if not adaylar:
            log("Uygun video bulunamadı. --donem ay ya da --min-izlenme 1000 dene.")
            sys.exit(1)
        log(f"    En viral {min(10, len(adaylar))} video ({a.sirala} sırasına göre):")
        for i, ad in enumerate(adaylar[:10], 1):
            kop = f"+{len(ad['kopyalar'])} kopya" if ad["kopyalar"] else ""
            print(f"    {i:2}. {sayi(ad['toplam_izlenme']):>6} izl | "
                  f"{sayi(ad['toplam_begeni']):>5} beğ | "
                  f"{PLATFORM_AD.get(ad['platform'], ad['platform'])[:9]:9} | "
                  f"{ad['kanal'][:16]:16} {kop:9} | {ad['baslik'][:42]}", flush=True)
        (CIKTI / "son_liste.json").write_text(json.dumps(adaylar, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        if a.sadece_liste:
            return

    yapilan = 0
    for ad in adaylar:
        if yapilan >= a.kac:
            break
        try:
            if isle(ad, a, yapilan + 1):
                yapilan += 1
        except Exception as e:
            log(f"    Bu video olmadı ({type(e).__name__}: {str(e)[:150]}), sıradakine geçiliyor")
        islendi_isaretle(ad)
    log(f"Bitti. {yapilan} video hazır: {CIKTI}")
    if yapilan == 0:
        sys.exit(1)


if __name__ == "__main__":
    import traceback
    _log = open(klipci.KOK / "son_calisma.log", "a", encoding="utf-8")
    sys.stdout = klipci._Tee(sys.stdout, _log)
    sys.stderr = klipci._Tee(sys.stderr, _log)
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        print("\nHATA: yukaridaki yaziyi Claude'a gonder.")
        sys.exit(1)
