<p align="center"><img src="app.png" width="96" alt="HK258 RGB logosu"></p>

<h1 align="center">HK258 RGB</h1>

<p align="center">Hawk HK258 klavye ve Hawk HM220 mouse için kontrol paneli — resmi sürücüsü olmayan klavyeye tersine mühendislikle yazıldı.</p>

> **Resmi değildir.** Bu proje Hawk Gaming ile bağlantılı değildir ve onlar tarafından desteklenmez.
> Klavyenin USB protokolü, üreticinin yazılımı olmadığı için deneme yoluyla çözülmüştür. Kullanım riski size aittir.

![Panel](docs/panel.png)

## Özellikler

- **Ana ekran:** klavye ve mouse kartları, pil durumlarıyla. Karta tıklayınca o cihazın ayarları
  animasyonla açılır (Esc ya da mouse'un geri tuşu ana ekrana döner)

**Klavye (HK258)**

- **4 mod:** Sabit renk, Nefes, Renk döngüsü ve klavyenin kendi gökkuşağı efekti
- Renk çarkı, hazır renkler, hex kodu girişi, parlaklık ve efekt hızı ayarı
- Klavyenin canlı önizlemesi (LCD ekranı ve ses düğmesiyle)
- **USB kablosu ve 2.4G alıcısı** ile çalışır; kablo takılıp çıkarılınca kendiliğinden geçiş yapar
- Pil yüzdesi ve bağlantı türü göstergesi

**Mouse (HM220)**

- Pil yüzdesi, şarj durumu, bağlantı (2.4G / kablolu); son bilinen pil değeri hatırlanır
- **DPI kademeleri:** 5 kademenin her birini 100–12000 DPI arası ayarlama, aktif kademeyi seçme
- **Raporlama hızı:** 125 / 250 / 500 / 1000 Hz (kablolu modda mouse hep 1000 Hz çalışır)
- Ayarlar mouse'un **kendi hafızasına** yazılır; uygulama kapalıyken de geçerli kalır
- Mouse'un DPI tuşuna basınca panel anında güncellenir

**Genel**

- **Windows açılışında** sistem tepsisinde sessizce başlar; kapatınca tepside çalışmaya devam eder
- Tek kopya: uygulama zaten açıksa ikinci kez açılmaz, mevcut panel öne gelir
- Kurulum sihirbazı (kurma / güncelleme / kaldırma)

## Desteklenen donanım

| Bağlantı | USB kimliği | Not |
|---|---|---|
| USB kablosu | `1A2C:B007` ("Gaming keyboard", Shinetek Technology) | |
| 2.4G alıcısı | `1A2C:8FFF` ("2.4 Wireless Device") | Komutları klavyeye iletir |
| Bluetooth | — | Desteklenmiyor (denenmedi) |

Aynı Shinetek denetleyicisini kullanan başka klavyelerde de çalışabilir, ama denenmedi.

| Mouse bağlantısı | USB kimliği | Not |
|---|---|---|
| 2.4G alıcısı | `1D57:FA60` ("HM220 2.4G") | Mouse 5 sn hareketsiz kalınca uyur; ayar okuma/yazma için biraz oynatmak gerekir |
| USB kablosu | `1D57:2027` ("HM220", Beken) | Kablo takılınca mouse ayrı bir cihaz olarak görünür |
| Bluetooth | — | Ayar kanalı yok |

## Kurulum

### Seçenek 1 — Python ile (önerilen)

Gerekenler: Windows 10/11, [Python 3.12+](https://www.python.org/downloads/)

```bash
python -m pip install -r requirements.txt
```

Ardından **`HK258 RGB Kurulum.pyw`** dosyasına çift tıklayın. Sihirbaz uygulamayı
`%LOCALAPPDATA%\Programs\HK258 RGB` klasörüne kurar, masaüstü ve Başlat menüsü kısayolu oluşturur
ve isterseniz Windows açılışına ekler. Eksik paket varsa kendisi kurar.

![Kurulum sihirbazı](docs/kurulum.png)

Komut satırından: `python kur.py` (kurar) · `python kur.py --kaldir` (kaldırır)

### Seçenek 2 — Tek dosya kurulum exe'si

```bash
python -m pip install pyinstaller -r requirements.txt
python derle.py
```

`Dagitim\HK258 RGB Kurulum.exe` oluşur: Python gerektirmeyen, tek dosyalık kurulum programı.
Uygulamayı **Ayarlar → Uygulamalar** listesine de ekler, oradan kaldırılabilir.

> **Not:** Exe imzasızdır. Windows 11'de **Akıllı Uygulama Denetimi** (Smart App Control) açıksa
> çalışmaz — o bilgisayarlarda Seçenek 1'i kullanın. İnternetten indirilen kopyada SmartScreen
> "Ek bilgi → Yine de çalıştır" isteyebilir.

## Kullanım

- Paneli masaüstündeki **HK258 RGB** kısayoluyla açın.
- Pencereyi kapatınca uygulama **sistem tepsisinde** çalışmaya devam eder ve rengi korur.
  Tamamen çıkmak için tepsi simgesine sağ tıklayıp **Çıkış**'ı seçin.
- Uygulama kapanınca klavye ~3 saniye içinde kendi gökkuşağı efektine döner.
- Klavyede **Fn + Esc** fabrika ayarlarına döndürür.

Komut satırı (`hk258_rgb.py`):

```bash
python hk258_rgb.py kirmizi        # hazır renk (kirmizi, yesil, mavi, beyaz, mor, turuncu, sari, pembe, turkuaz, kapali)
python hk258_rgb.py ff8800         # hex renk
python hk258_rgb.py 255 136 0      # R G B
python hk258_rgb.py pil            # pil yüzdesi ve bağlantı türü
```

## Protokol (tersine mühendislik notları)

Klavye, HID arayüzü `MI_00` (Usage Page `0xFF02`, report ID'siz 64 baytlık giriş/çıkış raporları)
üzerinden komut alır. 2.4G alıcısının da aynı arayüzü vardır ve komutları klavyeye iletir.

```
aa 55 cc 33 | KOMUT | veri (59 bayt)
```

| Komut | Anlamı |
|---|---|
| `0x0E` | Pil sorgusu. Cevap: `aa 55 cc 33 0e <pil %> <bağlantı>` (kablo: `03`, 2.4G: `01`). Klavye bu paketi ~7 sn'de bir kendiliğinden de gönderir; 2.4G alıcısı sorguya cevap vermez, periyodik paket kullanılır. |
| `0x00`, `0xB5`, `0xF0`, `0xF1`, `0xF4` | Bu sırayla, aynı veriyle gönderilince klavye **sabit renk** moduna geçer. Renk verinin başından itibaren `R G B R G B …` olarak tekrarlanır. |

- Sabit renk modu **geçicidir**: ~3 saniye yeni komut gelmezse klavye kendi efektine döner.
  Bu yüzden program rengi her saniye yeniden gönderir (keepalive). Renk kalıcı belleğe yazılmaz.
- Nefes ve renk döngüsü efektleri programda hesaplanıp klavyeye sürekli gönderilir (~6 kare/sn).
- Diğer komutlar sessizce yok sayılıyor ya da görünür bir etki yapmıyor; tam liste bilinmiyor.

### Mouse (HM220)

Mouse protokolü [hawk-hub-unofficial](https://github.com/WinTone01/hawk-hub-unofficial) projesinin
protokol belgesinden, PAW3311 DPI tablosu [attack-shark-x11-driver](https://github.com/HarukaYamamoto0/attack-shark-x11-driver)
projesinden alınmıştır (ikisi de MIT lisanslı). Okuma akışı, DPI çerçevesi ve checksum bu projede HM220
üzerinde yeniden doğrulandı.

USB arayüzü 2'de iki HID koleksiyonu var:

- **Olaylar** (Usage Page `0x000A`, input): `03 5c <tür> <p1> <p2>`. Tür `40` pil
  (`p1`: 1 pilde, 2 dolu, 3 şarj oluyor; `p2`: %), `10` DPI tuşu (`p1`: yeni kademe), `50` komut onayı.
- **Ayarlar** (Usage Page `0x000B`, feature): okumak için `A0 <rapor> <uzunluk> 00 01 00 00 00` gönderilir,
  ~250 ms sonra `A0` okunur (`a0 01` = izin), ardından rapor okunur. `0x04` DPI kademeleri
  (16 bit toplam checksum), `0x06` raporlama hızı (`06 09 01 v 255-v …`, `v = 1000 / Hz`).

Program yazmadan önce mouse'taki güncel ayarı okur, yalnızca değişen alanları değiştirir, onay bekler ve
sonra tekrar okuyup doğrular. 2.4G alıcısı mouse uyurken saatlerce paket göndermeyebildiği için
"mouse kullanılıyor mu" bilgisi Windows Raw Input ile alınır (yalnızca son hareket zamanı, hareket verisi saklanmaz).

## Dosyalar

| Dosya | Açıklama |
|---|---|
| `hk258_rgb.py` | Sürücü: protokol, keepalive, pil takibi, komut satırı |
| `hm220.py` | HM220 mouse: pil / bağlantı takibi, DPI ve raporlama hızı okuma-yazma |
| `hk258_panel.py` | Panel uygulaması (pywebview), sistem tepsisi, tek kopya, Windows açılışı |
| `panel.html` | Panel arayüzü |
| `HK258 RGB Kurulum.pyw` | Kurulum sihirbazı (tkinter) |
| `kur.py` | Kurulum / kaldırma adımları |
| `derle.py` | Tek dosya kurulum exe'sini derler (PyInstaller) |
| `make_icon.py` | `app.ico` / `app.png` logosunu üretir |

## Lisans

[MIT](LICENSE) — dilediğiniz gibi kullanabilir, değiştirebilir ve paylaşabilirsiniz; lisans metnini
korumanız yeterli. Yazılım "olduğu gibi" sunulur, hiçbir garanti verilmez.
