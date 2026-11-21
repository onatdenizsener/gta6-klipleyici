# GTA 6 Klipleyici

Uzun Twitch/YouTube yayınlarından en heyecanlı anları bulup **dikey (1080x1920), altyazılı, TikTok ve YouTube Shorts'a hazır** klipler çıkaran Windows aracı.

Yayın linkini veriyorsun, 20-25 dakika sonra paylaşmaya hazır 3 klip ve her biri için Türkçe başlık + hashtag hazır oluyor.

## Nasıl çalışıyor

```
Yayın linki
  │
  ├─ 1. Sesi indir ............ yt-dlp (sadece ses, hızlı)
  ├─ 2. Hype'ı bul ............ FFmpeg ses patlamaları + chat hızı (varsa)
  ├─ 3. Yazıya dök ............ Whisper (sadece aday anlar, tüm yayın değil)
  ├─ 4. Anları puanla ......... Claude Code (varsa) ya da kural tabanlı puan
  └─ 5. Klibi yap ............. sadece o dakikaları indir
                                 OpenCV facecam'i bulur → üstte cam, altta oyun
                                 kelime kelime İngilizce altyazı + altında Türkçe çeviri
                                 1080x1920 mp4 + aciklama.txt (TikTok / Shorts metni)
```

Yapay zekâ sadece 4. adımda (hangi an iyi?) kullanılıyor. Geri kalan her şey bilgisayarda çalışan ücretsiz araçlar.

## Kurulum (Windows, tek seferlik)

1. Python 3.10+ kurulu olsun (Anaconda da olur).
2. **`kurulum.bat`** dosyasına çift tıkla. Sanal ortamı `%LOCALAPPDATA%\gta6klip` altına kurar, paketleri yükler, FFmpeg yoksa `winget` ile kurar.
3. "KURULUM TAMAM" yazısını görünce kapat.

İlk klipte Whisper modeli bir kez iner (~500 MB).

## Kullanım

**`klip.bat`** dosyasına çift tıkla, **bitmiş** bir yayının linkini yapıştır, Enter'a bas.

- Twitch: kanal → Videolar → Geçmiş yayınlar → `https://www.twitch.tv/videos/123456789`
- YouTube: kanal → Canlı sekmesi → bitmiş yayın

Canlı yayın linki verirsen program bunu söyleyip durur.

Çıktı:

```
klipler_cikti/
  <yayinci>_<id>/
    adaylar.json                 bulunan tüm aday anlar, transkript ve puanlarla
    klip1_01-38-45_puan8.5/
      klip1_01-38-45_puan8.5.mp4 paylaşılacak dikey video
      aciklama.txt               TikTok + YouTube Shorts başlık, açıklama, hashtag
      altyazi.ass
```

## Seçenekler

Komut satırından `klip.bat` ile birlikte:

| Seçenek | Ne yapar |
|---|---|
| `--kac 5` | 5 klip çıkar (varsayılan 3) |
| `--altyazi ikili` | İngilizce + altında Türkçe (varsayılan) |
| `--altyazi tr` | Sadece büyük Türkçe altyazı |
| `--altyazi en` | Sadece İngilizce |
| `--model base` | Daha hızlı, altyazı biraz daha kötü |
| `--model medium` | Daha iyi altyazı, daha yavaş |
| `--chat-dk 0` | Chat'i hiç kullanma (çok uzun yayınlarda hızlandırır) |
| `--sadece-analiz` | Klip yapma, sadece `adaylar.json` yaz |
| `--secim 2,5,9` | `adaylar.json` içindeki şu adaylardan klip yap |
| `--claude-yok` | Claude ile puanlamayı atla |

## Notlar

- **Claude ile puanlama:** Bilgisayarda [Claude Code](https://claude.com/claude-code) (`claude` komutu) kuruluysa anları Claude puanlar ve Türkçe başlık önerir. Yoksa kural tabanlı puan kullanılır.
- **Çeviri:** Google Translate → MyMemory → Claude sırasıyla denenir.
- **Twitch telif sessizlikleri:** Twitch'in sesi kapattığı bölümler otomatik eleniyor, sahte "ses patlaması" sayılmıyor.
- **Ses önbelleği:** İndirilen ses `%LOCALAPPDATA%\gta6klip\ses` altında tutulur, aynı yayını tekrar işlerken yeniden inmez. Yer açmak için o klasörü silebilirsin.
- **Log:** Her çalıştırma `son_calisma.log` dosyasına yazılır.

## Telif ve izin

Başkasının yayınından klip paylaşıp para kazanacaksan yayıncının klip programı ya da izni olduğundan emin ol. İzinsiz kullanım telif şikâyetine yol açabilir. Bu araç sadece kesme ve düzenleme işini otomatikleştirir, içerik hakları yayıncıya aittir.
