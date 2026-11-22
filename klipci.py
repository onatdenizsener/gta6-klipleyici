# -*- coding: utf-8 -*-
"""
GTA 6 Klipleyici
Yayin linki (Twitch VOD / YouTube) veya yerel video dosyasi verirsin,
en heyecanli anlari bulur ve dikey, altyazili, paylasima hazir klipler cikarir.

Adimlar:
 1. Sesi indir (yt-dlp, sadece ses)
 2. Hype'i bul: ses yuksekligi patlamalari + chat hizi (varsa)
 3. Sadece aday pencereleri Whisper ile yaziya dok (hizli)
 4. Anlari puanla: Claude Code (claude komutu varsa) yoksa kural tabanli
 5. Klibi yap: sadece o dakikalari indir, facecam ustte, oyun altta,
    kelime kelime altyazi, 1080x1920 mp4
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

SURUM = 2
KOK = Path(__file__).resolve().parent
CIKTI = KOK / "klipler_cikti"

HYPE_KELIMELER = [
    # ingilizce yayinci tepkileri
    "no way", "oh my god", "omg", "what the", "wtf", "holy", "let's go", "lets go",
    "insane", "crazy", "bro", "dude", "yo", "clip that", "clip it", "chat", "look at",
    "are you kidding", "no shot", "dead", "ran over", "cops", "police", "wanted",
    "vice city", "lucia", "jason", "heist", "explode", "boom", "hahaha", "laugh",
    "i can't believe", "can't believe", "unbelievable", "first time", "secret",
    "easter egg", "glitch", "bug", "physics",
]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def ffmpeg_yolu():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    if winget.exists():
        return str(winget)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("FFmpeg bulunamadi. Once kurulum.bat calistir.")


FFMPEG = None


def calistir(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stderr[-3000:])
        raise RuntimeError(f"Komut basarisiz: {' '.join(map(str, cmd[:4]))} ...")
    return r


def sn_to_ts(s):
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def guvenli_ad(s, n=40):
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.UNICODE).strip().replace(" ", "_")
    return (s or "yayin")[:n]


# ---------------------------------------------------------------- 1. indirme
def bilgi_al(url):
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as y:
        return y.extract_info(url, download=False)


_son_yuzde = [-10]


def _ilerleme(d):
    if d.get("status") != "downloading":
        return
    top = d.get("total_bytes") or d.get("total_bytes_estimate")
    if not top:
        return
    y = int(100 * d.get("downloaded_bytes", 0) / top)
    if y >= _son_yuzde[0] + 10:
        _son_yuzde[0] = y - y % 10
        print(f"    indirildi: %{_son_yuzde[0]}", flush=True)


def ses_indir(url, hedef: Path):
    import yt_dlp
    if hedef.exists():
        return hedef
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(hedef.with_suffix(".%(ext)s")),
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [_ilerleme],
        "ffmpeg_location": FFMPEG,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}],
    }
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    adaylar = list(hedef.parent.glob(hedef.stem + ".*"))
    adaylar = [a for a in adaylar if a.suffix in (".m4a", ".mp3", ".opus", ".webm", ".aac")]
    if not adaylar:
        raise RuntimeError("Ses indirilemedi")
    adaylar[0].rename(hedef)
    return hedef


# ---------------------------------------------------------------- 2. hype
def ses_yuksekligi(ses: Path):
    """Saniye basina dB (8 kHz mono PCM uzerinden RMS)."""
    sr = 8000
    p = subprocess.Popen([FFMPEG, "-v", "error", "-i", str(ses), "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], stdout=subprocess.PIPE)
    db = []
    while True:
        b = p.stdout.read(sr * 2 * 60)  # 60 sn'lik parca
        if not b:
            break
        a = np.frombuffer(b, dtype=np.int16).astype(np.float32)
        n = len(a) // sr
        if n == 0:
            continue
        a = a[: n * sr].reshape(n, sr)
        rms = np.sqrt((a ** 2).mean(axis=1)) + 1e-6
        db.extend((20 * np.log10(rms / 32768)).tolist())
    p.wait()
    return np.array(db)


def chat_hizi(url, sure, limit_dk=4):
    """Saniye basina chat mesaji sayisi. limit_dk icinde bitmezse None (sadece ses)."""
    try:
        from chat_downloader import ChatDownloader
    except Exception:
        return None
    import threading
    import time
    say = np.zeros(int(sure) + 1)
    durum = {"bitti": False, "hata": None, "toplam": 0, "son_t": 0}

    def calis():
        try:
            chat = ChatDownloader().get_chat(url, message_types=["text_message"])
            for m in chat:
                t = m.get("time_in_seconds")
                if t is None or t < 0 or t > sure:
                    continue
                say[int(t)] += 1
                durum["toplam"] += 1
                durum["son_t"] = t
            durum["bitti"] = True
        except Exception as e:
            durum["hata"] = e

    log(f"Chat indiriliyor (en fazla {limit_dk} dk, bitmezse sadece ses kullanilir)...")
    th = threading.Thread(target=calis, daemon=True)
    th.start()
    bitis = time.time() + limit_dk * 60
    while th.is_alive() and time.time() < bitis:
        th.join(max(0.1, min(30, bitis - time.time())))
        if th.is_alive():
            print(f"    chat: {durum['toplam']} mesaj, yayinin "
                  f"%{100 * durum['son_t'] / max(sure, 1):.0f}'i", flush=True)
    if durum["hata"]:
        log(f"Chat alinamadi, sadece ses kullanilacak ({type(durum['hata']).__name__})")
        return None
    if not durum["bitti"]:
        log(f"Chat {limit_dk} dakikada bitmedi (yayin cok uzun/kalabalik) -> sadece ses kullaniliyor")
        return None
    log(f"Chat: {durum['toplam']} mesaj")
    return say if durum["toplam"] > 50 else None


def z(x):
    s = x.std()
    return (x - x.mean()) / (s if s > 1e-9 else 1)


def kaydir(x, w):
    if w <= 1:
        return x
    k = np.ones(w) / w
    return np.convolve(x, k, mode="same")


def hype_adaylari(db, chat, aday_sayisi=15, pencere=45):
    n = len(db)
    ham = db
    # Twitch'in telif yuzunden sustugu kisimlar -200 dB gibi gelir; kirp ki
    # ses geri acildiginda sahte "patlama" sayilmasin
    db = np.clip(db, -60, 0)
    sessiz_ham = ham < -50
    # klip penceresinin (tepe-35 .. tepe+30) icinde sessizlik olan anlari ele
    sessiz = np.zeros(n, dtype=bool)
    idx = np.flatnonzero(sessiz_ham)
    if len(idx):
        cs = np.concatenate([[0], np.cumsum(sessiz_ham)])
        for i in range(n):
            a, b = max(0, i - 35), min(n, i + 30)
            sessiz[i] = (cs[b] - cs[a]) > 3
    # yerel ortalamaya gore patlama (yayincinin genel ses seviyesinden bagimsiz)
    ok = (~sessiz_ham).astype(float)
    yerel = kaydir(db * ok, 180) / np.maximum(kaydir(ok, 180), 1e-3)
    yerel[sessiz_ham] = db[sessiz_ham]
    patlama = kaydir(db - yerel, 4)
    puan = z(patlama)
    if chat is not None:
        c = np.zeros(n)
        m = min(n, len(chat))
        c[:m] = chat[:m]
        c = kaydir(c, 10)
        # chat tepkisi gecikmeli gelir: 8 sn geri kaydir
        c = np.roll(c, -8)
        c_rel = c / (kaydir(c, 300) + 0.5)
        puan = 0.55 * puan + 0.45 * z(c_rel)
    puan[sessiz] = puan.min()
    # uzun yayinlarda ilk 8 dk genelde "basliyoruz", menu, sohbet
    baslangic = 480 if n > 2400 else 15
    secilen = []
    sira = np.argsort(-puan)
    for i in sira:
        if len(secilen) >= aday_sayisi:
            break
        if i < baslangic or i > n - 10 or sessiz[i]:
            continue
        if any(abs(i - s) < pencere + 15 for s, _ in secilen):
            continue
        secilen.append((int(i), float(puan[i])))
    adaylar = []
    for tepe, p in sorted(secilen):
        bas = max(0, tepe - 30)
        son = min(n, tepe + 25)
        adaylar.append({
            "tepe": tepe, "bas": bas, "son": son, "hype": round(p, 2),
            "ses_db": round(float(patlama[tepe]), 1),
            "chat_x": None if chat is None else round(float(
                kaydir(chat[: n].astype(float), 10)[min(tepe, len(chat) - 1)] /
                (np.mean(chat) + 1e-6)), 1),
        })
    return adaylar


# ---------------------------------------------------------------- 3. whisper
_MODEL = None


def whisper_model(boyut):
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        log(f"Whisper modeli yukleniyor ({boyut})...")
        _MODEL = WhisperModel(boyut, device="cpu", compute_type="int8")
    return _MODEL


def parca_kes(ses, bas, son, hedef):
    calistir([FFMPEG, "-y", "-v", "error", "-ss", str(bas), "-to", str(son), "-i", str(ses),
              "-ac", "1", "-ar", "16000", str(hedef)])


def yaziya_dok(wav, boyut, kelime=False):
    model = whisper_model(boyut)
    segs, info = model.transcribe(str(wav), vad_filter=True, word_timestamps=kelime,
                                  beam_size=1)
    out = []
    for s in segs:
        d = {"bas": round(s.start, 2), "son": round(s.end, 2), "metin": s.text.strip()}
        if kelime and s.words:
            d["kelimeler"] = [{"bas": round(w.start, 2), "son": round(w.end, 2),
                               "k": w.word.strip()} for w in s.words]
        out.append(d)
    return out, info.language


# ---------------------------------------------------------------- 4. puanlama
def kural_puani(a):
    metin = " ".join(s["metin"] for s in a.get("transkript", [])).lower()
    k = sum(metin.count(w) for w in HYPE_KELIMELER)
    unlem = metin.count("!")
    p = 4 + 0.9 * min(a["hype"], 4) + min(k, 6) * 0.4 + min(unlem, 4) * 0.2
    if a.get("chat_x"):
        p += min(a["chat_x"], 6) * 0.3
    if len(metin) < 20:
        p -= 1.5
    return round(max(0, min(10, p)), 1)


def claude_var():
    return shutil.which("claude") is not None


def claude_sor(prompt, timeout=600):
    """claude -p, prompt stdin'den (Windows'ta cok satirli arguman bozuluyor)."""
    r = subprocess.run("claude -p" if os.name == "nt" else ["claude", "-p"], input=prompt,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, shell=(os.name == "nt"))
    try:
        (KOK / "claude_cikti.txt").write_text(
            f"komut: {shutil.which('claude')}\nkod: {r.returncode}\n--- stdout ---\n"
            f"{r.stdout[-4000:]}\n--- stderr ---\n{r.stderr[-4000:]}\n", encoding="utf-8")
    except Exception:
        pass
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError(r.stderr[-500:])
    return r.stdout


def claude_puanla(adaylar, baslik, kac):
    satirlar = []
    for i, a in enumerate(adaylar):
        metin = " ".join(f"[{sn_to_ts(a['bas'] + s['bas'])}] {s['metin']}"
                         for s in a.get("transkript", []))
        satirlar.append(f"ADAY {i} | {sn_to_ts(a['bas'])}-{sn_to_ts(a['son'])} | "
                        f"ses patlamasi {a['ses_db']:+} dB | chat x{a['chat_x']}\n{metin}")
    prompt = f"""Sen viral kisa video klipleyicisisin. Yayin: "{baslik}" (GTA 6).
Asagida yayindan aday anlar var (zaman damgali transkript + ses/chat sinyali).
Her adayi 0-10 arasi SERT puanla: sadece baglam gerektirmeden komik, sok edici,
epik ya da tepki dolu anlar 7+ alir. Sikici, anlasilmaz, sadece gurultu olanlar dusuk.
Her aday icin klibin en iyi baslangic ve bitis saniyesini (aday araligi icinde, 15-60 sn)
ve TikTok/Shorts icin kisa, buyuk harfli Ingilizce bir baslik, Turk izleyici icin
merak uyandiran buyuk harfli Turkce bir baslik + 4 hashtag oner.
SADECE su formatta JSON don, baska hicbir sey yazma:
{{"adaylar":[{{"i":0,"puan":7.5,"bas":"01:02:03","son":"01:02:40","baslik":"...","baslik_tr":"...","hashtag":"#gta6 ..."}}]}}

{chr(10).join(satirlar)}"""
    try:
        r = claude_sor(prompt, 900)
        m = re.search(r"\{.*\}", r, re.S)
        veri = json.loads(m.group(0))
        for d in veri["adaylar"]:
            a = adaylar[int(d["i"])]
            a["puan"] = float(d["puan"])
            a["puanlayan"] = "claude"
            a["baslik"] = d.get("baslik", "")
            a["baslik_tr"] = d.get("baslik_tr", "")
            a["hashtag"] = d.get("hashtag", "#gta6 #gta6clips #gaming #fyp")
            for anahtar in ("bas", "son"):
                if d.get(anahtar):
                    h, mi, s = [int(x) for x in d[anahtar].split(":")]
                    a[anahtar + "_klip"] = h * 3600 + mi * 60 + s
        return True
    except Exception as e:
        log(f"Claude ile puanlama olmadi ({type(e).__name__}: {str(e)[:150]}), kural tabanli "
            f"puan kullaniliyor. Ayrinti: claude_cikti.txt")
        return False


# ---------------------------------------------------------------- 5. render
def video_parca_indir(url, bas, son, hedef: Path):
    import yt_dlp
    from yt_dlp.utils import download_range_func
    opts = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "outtmpl": str(hedef.with_suffix(".%(ext)s")),
        "quiet": True,
        "noprogress": True,
        "ffmpeg_location": FFMPEG,
        "download_ranges": download_range_func(None, [(bas, son)]),
        "force_keyframes_at_cuts": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    for f in hedef.parent.glob(hedef.stem + ".*"):
        if f.suffix in (".mp4", ".mkv", ".webm"):
            return f
    raise RuntimeError("Video parcasi indirilemedi")


def facecam_bul(video: Path):
    """Facecam kutusunu tahmin eder: (x, y, w, h) veya None."""
    import cv2
    cap = cv2.VideoCapture(str(video))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    try:
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if det.empty():
            raise RuntimeError
    except Exception:
        cap.release()
        return None, W, H
    kutular, bakilan = [], 0
    for k in range(12):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / 12))
        ok, fr = cap.read()
        if not ok:
            continue
        bakilan += 1
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        yuz = det.detectMultiScale(g, 1.1, 6, minSize=(int(H * 0.05), int(H * 0.05)))
        if len(yuz):
            kutular.append(max(yuz, key=lambda b: b[2] * b[3]))
    cap.release()
    if bakilan == 0 or len(kutular) < max(3, bakilan * 0.4):
        return None, W, H
    x, y, w, h = np.median(np.array(kutular), axis=0)
    # yuz ekranin buyuk kismini kapliyorsa (sadece kamera yayini) facecam modu yok
    if w > W * 0.35:
        return None, W, H
    cw = min(W, w * 3.2)
    ch = min(H, cw * 9 / 16 * 1.0)
    cx, cy = x + w / 2, y + h / 2
    x0 = int(min(max(0, cx - cw / 2), W - cw))
    y0 = int(min(max(0, cy - ch / 2), H - ch))
    return (x0, y0, int(cw) // 2 * 2, int(ch) // 2 * 2), W, H


def ass_zaman(t):
    t = max(0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def tr_upper(t):
    return t.replace("i", "İ").replace("ı", "I").upper()


def cevir_tr(metinler, kaynak="en"):
    """Satirlari Turkceye cevirir (kaynak dil varsayilan Ingilizce, 'auto' da olur).
    Once Google Translate, olmazsa MyMemory, olmazsa Claude."""
    if not metinler:
        return []
    import time
    import requests
    temiz = [m.replace("\n", " ").strip() or "..." for m in metinler]
    hatalar = []
    kaynak = kaynak or "auto"

    def gtx(metin):
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": kaynak, "tl": "tr", "dt": "t", "q": metin},
                         timeout=20)
        r.raise_for_status()
        return "".join(p[0] for p in r.json()[0] if p and p[0])

    def deep(metin):
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source=kaynak, target="tr").translate(metin)

    def mymemory(metin):
        from deep_translator import MyMemoryTranslator
        return MyMemoryTranslator(source="en-US" if kaynak in ("en", "auto") else kaynak,
                                  target="tr-TR").translate(metin)

    for ad, f in (("google-api", gtx), ("google", deep)):
        for deneme in range(2):
            try:
                parca = [t.strip() for t in (f("\n".join(temiz)) or "").split("\n")]
                if len(parca) == len(metinler):
                    return parca
                # satirlar birlesti: tek tek cevir
                out = []
                for m in temiz:
                    out.append((f(m) or "").strip())
                    time.sleep(0.3)
                return out
            except Exception as e:
                hatalar.append(f"{ad}:{type(e).__name__}")
                time.sleep(3)
    try:
        out = [(mymemory(m) or "").strip() for m in temiz]
        if any(out):
            return out
    except Exception as e:
        hatalar.append(f"mymemory:{type(e).__name__}")
    log(f"    Ceviri servisleri olmadi ({', '.join(hatalar)})")
    if claude_var():
        try:
            prompt = ("Asagidaki video konusmasi satirlarini dogal, gunluk, yayinci agzi "
                      "Turkceye cevir. Kufurleri yumusat. Ayni sirada, satir sayisi ayni, "
                      "SADECE JSON liste don: [\"...\", ...]\n" +
                      json.dumps(metinler, ensure_ascii=False))
            out = json.loads(re.search(r"\[.*\]", claude_sor(prompt, 300), re.S).group(0))
            if len(out) == len(metinler):
                return out
        except Exception:
            pass
    log("    Ceviri yapilamadi, sadece Ingilizce altyazi")
    return None


def cumleler(kelimeler, en_fazla=7):
    """Kelime listesini cevrilecek kisa cumle parcalarina boler."""
    out, g = [], []
    for w in kelimeler:
        g.append(w)
        if len(g) >= en_fazla or w["k"].endswith((".", "!", "?")):
            out.append(g)
            g = []
    if g:
        out.append(g)
    return [{"bas": g[0]["bas"], "son": g[-1]["son"],
             "en": " ".join(w["k"] for w in g)} for g in out]


def altyazi_yaz(kelimeler, hedef: Path, y_konum, mod="ikili", tr_parcalar=None):
    bas = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ana,Arial Black,{84 if mod == "en" else 70},&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: TR,Arial Black,{80 if mod == "tr" else 58},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{7 if mod == "tr" else 5},3,5,70,70,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    satir = []
    if mod in ("en", "ikili"):
        gruplar, grup = [], []
        for w in kelimeler:
            grup.append(w)
            if len(grup) >= 3 or w["k"].endswith((".", "!", "?", ",")):
                gruplar.append(grup)
                grup = []
        if grup:
            gruplar.append(grup)
        olaylar = []
        for g in gruplar:
            for j, w in enumerate(g):
                parcalar = []
                for kk, ww in enumerate(g):
                    t = ww["k"].upper().replace("{", "").replace("}", "")
                    parcalar.append("{\\c&H00FFFF&}" + t + "{\\c&HFFFFFF&}" if kk == j else t)
                son = g[j + 1]["bas"] if j + 1 < len(g) else w["son"] + 0.15
                olaylar.append([w["bas"], son, " \\h".join(parcalar)])
        for i in range(len(olaylar) - 1):
            olaylar[i][1] = min(olaylar[i][1], olaylar[i + 1][0])
        satir += [f"Dialogue: 0,{ass_zaman(b)},{ass_zaman(e)},Ana,,0,0,0,,"
                  f"{{\\pos(540,{y_konum})}}{t}" for b, e, t in olaylar if e > b]
    if tr_parcalar and mod in ("tr", "ikili"):
        y_tr = y_konum if mod == "tr" else y_konum + 125
        renk = "" if mod == "tr" else "{\\c&H9DF5FF&}"
        tp = [dict(p) for p in tr_parcalar]
        for i in range(len(tp)):
            sonraki = tp[i + 1]["bas"] if i + 1 < len(tp) else tp[i]["son"] + 0.6
            tp[i]["son"] = min(max(tp[i]["son"] + 0.4, tp[i]["bas"] + 1.0), sonraki)
        for p in tp:
            t = tr_upper(p.get("tr", "").replace("{", "").replace("}", ""))
            if t and p["son"] > p["bas"]:
                satir.append(f"Dialogue: 1,{ass_zaman(p['bas'])},{ass_zaman(p['son'])},TR,,0,0,0,,"
                             f"{{\\pos(540,{y_tr})}}{renk}{t}")
    hedef.write_text(bas + "\n".join(satir) + "\n", encoding="utf-8")


def klip_render(kaynak: Path, cikis: Path, kelimeler, cam, mod="ikili", tr_parcalar=None):
    cam_kutu, W, H = cam
    calisma = cikis.parent
    ass = calisma / "altyazi.ass"
    if cam_kutu:
        x, y, w, h = cam_kutu
        ust_h = 640
        alt_h = 1920 - ust_h
        # oyun: facecam haric ortadan dikey kesit
        gw = int(H * 1080 / alt_h) // 2 * 2
        gw = min(gw, W)
        gx = (W - gw) // 2
        filt = (f"[0:v]crop={w}:{h}:{x}:{y},scale=1080:{ust_h}:force_original_aspect_ratio=increase,"
                f"crop=1080:{ust_h}[cam];"
                f"[0:v]crop={gw}:{H}:{gx}:0,scale=1080:{alt_h}:force_original_aspect_ratio=increase,"
                f"crop=1080:{alt_h}[oyun];"
                f"[cam][oyun]vstack=inputs=2[v0]")
        y_alt = ust_h + 120
    else:
        filt = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                "boxblur=25:2,eq=brightness=-0.15[bg];"
                "[0:v]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2[v0]")
        y_alt = 1440
    if kelimeler:
        altyazi_yaz(kelimeler, ass, y_alt, mod, tr_parcalar)
        filt += ";[v0]subtitles=altyazi.ass[v]"
    else:
        filt += ";[v0]null[v]"
    def cmd(f):
        return [FFMPEG, "-y", "-v", "error", "-i", str(kaynak), "-filter_complex", f,
                "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "21", "-r", "30", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", cikis.name]
    try:
        calistir(cmd(filt), cwd=calisma)
    except RuntimeError:
        if "subtitles=" not in filt:
            raise
        log("    FFmpeg altyazi desteklemiyor, altyazisiz yapiliyor")
        calistir(cmd(filt.replace("subtitles=altyazi.ass", "null")), cwd=calisma)


def aciklama_yaz(ad, kelimeler, tr_parcalar, kaynak, bas, yayin_baslik):
    en = ad.get("baslik") or " ".join(w["k"] for w in kelimeler[:8]).upper() or "GTA 6 MOMENT"
    tr = ad.get("baslik_tr")
    if not tr and tr_parcalar:
        tr = tr_upper(max((p.get("tr", "") for p in tr_parcalar), key=len)[:70])
    tr = tr or en
    yayinci = re.sub(r"\s+", " ", str(yayin_baslik))[:60]
    tik = "#gta6 #gta6türkiye #gta6klip #gta #oyun #keşfet #fyp"
    yt = "#gta6 #gta6türkiye #shorts"
    return (f"=== TIKTOK ===\n{tr} 😳 {tik}\n\n"
            f"=== YOUTUBE SHORTS ===\nBaslik (max 100 karakter):\n{tr[:85]} #shorts\n\n"
            f"Aciklama:\n{tr}\n({en})\n\nKaynak yayin: {kaynak} ({sn_to_ts(bas)})\n{yt}\n\n"
            f"=== NOT ===\nYayin: {yayinci}\n"
            f"Puan: {ad.get('puan')} ({ad.get('puanlayan')})\n")


# ---------------------------------------------------------------- ana akis
def main():
    global FFMPEG
    ap = argparse.ArgumentParser(description="GTA 6 yayin klipleyici")
    ap.add_argument("kaynak", help="Twitch VOD / YouTube linki ya da yerel video dosyasi")
    ap.add_argument("--kac", type=int, default=3, help="Kac klip cikarilsin (varsayilan 3)")
    ap.add_argument("--min-puan", type=float, default=7.0)
    ap.add_argument("--model", default="small", help="Whisper modeli: tiny/base/small/medium")
    ap.add_argument("--aday", type=int, default=0, help="Puanlanacak aday an sayisi (0=otomatik)")
    ap.add_argument("--chat-dk", type=float, default=4,
                    help="Chat indirmeye en fazla kac dakika (0 = chat kullanma)")
    ap.add_argument("--sadece-analiz", action="store_true",
                    help="Klip uretme, sadece adaylar.json yaz")
    ap.add_argument("--secim", help="adaylar.json icindeki aday numaralari, orn. 2,5,9")
    ap.add_argument("--claude-yok", action="store_true", help="Claude ile puanlamayi atla")
    ap.add_argument("--altyazi", default="ikili", choices=["ikili", "tr", "en"],
                    help="ikili: Ingilizce + altinda Turkce (varsayilan), tr: sadece Turkce, "
                         "en: sadece Ingilizce")
    a = ap.parse_args()

    FFMPEG = ffmpeg_yolu()
    yerel = Path(a.kaynak).exists()
    if yerel:
        kaynak_yol = Path(a.kaynak).resolve()
        baslik, vid = kaynak_yol.stem, guvenli_ad(kaynak_yol.stem)
    else:
        log("Yayin bilgisi aliniyor...")
        info = bilgi_al(a.kaynak)
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            print("\nBU BIR CANLI YAYIN. Canli yayin bitmeden ses inmeyi bitiremez.\n"
                  "Bitmis bir yayinin linkini ver:\n"
                  "  Twitch: kanal sayfasi > Videolar > Gecmis yayinlar > linki kopyala\n"
                  "          (twitch.tv/videos/123456789 gibi olmali)\n"
                  "  YouTube: kanal > Canli sekmesi > bitmis yayin\n")
            sys.exit(1)
        baslik = info.get("title") or "yayin"
        vid = guvenli_ad(f"{info.get('uploader', '')}_{info.get('id', '')}")
        log(f"Yayin: {baslik} ({sn_to_ts(info.get('duration') or 0)})")
    is_dir = CIKTI / vid
    is_dir.mkdir(parents=True, exist_ok=True)
    adaylar_json = is_dir / "adaylar.json"

    veri = None
    if adaylar_json.exists() and (a.secim or not a.sadece_analiz):
        veri = json.loads(adaylar_json.read_text(encoding="utf-8"))
        if veri.get("surum") != SURUM and not a.secim:
            veri = None
    if veri:
        adaylar = veri["adaylar"]
        log(f"Onceki analiz kullaniliyor ({len(adaylar)} aday)")
    else:
        # 1. ses
        if yerel:
            ses = kaynak_yol
        else:
            log("1/5 Ses indiriliyor (sadece ses, hizli)...")
            onbellek = Path(os.environ.get("LOCALAPPDATA") or KOK) / "gta6klip" / "ses" / vid
            onbellek.mkdir(parents=True, exist_ok=True)
            ses = ses_indir(a.kaynak, onbellek / "ses.m4a")
        # 2. hype
        log("2/5 Ses yuksekligi analiz ediliyor...")
        db = ses_yuksekligi(ses)
        log(f"    {sn_to_ts(len(db))} ses tarandi")
        chat = None if (yerel or a.chat_dk <= 0) else chat_hizi(a.kaynak, len(db), a.chat_dk)
        aday_n = a.aday or int(min(30, max(15, len(db) / 1800)))
        adaylar = hype_adaylari(db, chat, aday_n)
        log(f"    {len(adaylar)} aday an bulundu")
        # 3. whisper
        log(f"3/5 Aday anlar yaziya dokuluyor (Whisper {a.model})...")
        for i, ad in enumerate(adaylar):
            wav = is_dir / f"_aday{i}.wav"
            parca_kes(ses, ad["bas"], ad["son"], wav)
            ad["transkript"], _ = yaziya_dok(wav, a.model)
            wav.unlink(missing_ok=True)
            print(f"    aday {i + 1}/{len(adaylar)} [{sn_to_ts(ad['bas'])}]", flush=True)
        # 4. puan
        log("4/5 Anlar puanlaniyor...")
        for ad in adaylar:
            ad["puan"] = kural_puani(ad)
            ad["puanlayan"] = "kural"
        if not a.claude_yok and claude_var():
            log("    Claude Code bulundu, Claude puanliyor...")
            claude_puanla(adaylar, baslik, a.kac)
        elif not a.claude_yok:
            log("    'claude' komutu yok -> kural tabanli puan. (Claude sohbetinde "
                "'adaylari puanla' diyerek Claude'a da puanlatabilirsin.)")
        adaylar_json.write_text(json.dumps({"surum": SURUM, "kaynak": a.kaynak, "baslik": baslik,
                                            "adaylar": adaylar}, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        log(f"    Adaylar kaydedildi: {adaylar_json}")

    if a.sadece_analiz:
        return

    # secim
    if a.secim:
        secilen = [adaylar[int(i)] for i in a.secim.split(",")]
    else:
        sirali = sorted(adaylar, key=lambda x: -x["puan"])
        secilen = [x for x in sirali if x["puan"] >= a.min_puan][: a.kac]
        if not secilen:
            secilen = sirali[: a.kac]
            log(f"    {a.min_puan}+ puan alan an yok, en iyi {a.kac} alindi")

    # 5. render
    log(f"5/5 {len(secilen)} klip yapiliyor...")
    for k, ad in enumerate(secilen, 1):
        bas = ad.get("bas_klip", ad["bas"])
        son = ad.get("son_klip", ad["son"])
        if son - bas < 10:
            bas, son = ad["bas"], ad["son"]
        ad_klip = f"klip{k}_{sn_to_ts(bas).replace(':', '-')}_puan{ad['puan']}"
        kd = is_dir / ad_klip
        kd.mkdir(exist_ok=True)
        log(f"  Klip {k}: {sn_to_ts(bas)}-{sn_to_ts(son)} (puan {ad['puan']}, {ad['puanlayan']})")
        if yerel:
            parca = kd / "kaynak.mp4"
            calistir([FFMPEG, "-y", "-v", "error", "-ss", str(bas), "-to", str(son),
                      "-i", str(kaynak_yol), "-c:v", "libx264", "-preset", "veryfast",
                      "-crf", "18", "-c:a", "aac", str(parca)])
        else:
            parca = video_parca_indir(a.kaynak, bas, son, kd / "kaynak")
        wav = kd / "_ses.wav"
        calistir([FFMPEG, "-y", "-v", "error", "-i", str(parca), "-ac", "1", "-ar", "16000",
                  str(wav)])
        try:
            seg, _ = yaziya_dok(wav, a.model, kelime=True)
            kelimeler = [w for s in seg for w in s.get("kelimeler", [])]
        except Exception as e:
            log(f"    altyazi atlandi ({type(e).__name__})")
            kelimeler = []
        wav.unlink(missing_ok=True)
        tr_parcalar = None
        if kelimeler and a.altyazi != "en":
            tr_parcalar = cumleler(kelimeler)
            ceviri = cevir_tr([p["en"] for p in tr_parcalar])
            if ceviri:
                for p, t in zip(tr_parcalar, ceviri):
                    p["tr"] = t
                log(f"    {len(tr_parcalar)} satir Turkceye cevrildi")
            else:
                tr_parcalar = None
        mod = a.altyazi if tr_parcalar else "en"
        cam = facecam_bul(parca)
        log("    facecam bulundu -> ust/alt duzen" if cam[0] else
            "    facecam yok -> bulanik arka planli duzen")
        cikis = kd / f"{ad_klip}.mp4"
        klip_render(parca, cikis, kelimeler, cam, mod, tr_parcalar)
        (kd / "aciklama.txt").write_text(aciklama_yaz(ad, kelimeler, tr_parcalar, a.kaynak, bas,
                                                      baslik), encoding="utf-8")
        parca.unlink(missing_ok=True)
        log(f"    HAZIR: {cikis}")
    log(f"Bitti. Klipler: {is_dir}")


class _Tee:
    def __init__(self, a, b):
        self.a, self.b = a, b

    def write(self, s):
        for x in (self.a, self.b):
            try:
                x.write(s)
                x.flush()
            except Exception:
                pass

    def flush(self):
        pass


if __name__ == "__main__":
    import traceback
    _log = open(KOK / "son_calisma.log", "a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, _log)
    sys.stderr = _Tee(sys.stderr, _log)
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        print("\nHATA: yukaridaki yaziyi Claude'a gonder.")
        sys.exit(1)
