# Social Media Data Scraper

Backend FastAPI untuk mengumpulkan data publik dari X (Twitter) dan Threads
berdasarkan keyword atau URL postingan.

## Fitur

- Scraping X dan Threads.
- Pencarian `latest` atau `top`.
- Pengumpulan postingan dan komentar/reply.
- Input keyword atau direct URL.
- Persistent browser session untuk X dan Threads.
- Login interaktif melalui browser native.
- Headless maupun headed browser.
- Infinite scroll dan lazy-loading scan.
- Filter teks sistem dan deduplikasi.
- Checkpoint dan export CSV UTF-8-SIG.
- Background job dengan status `queued`, `running`, `success`, dan `error`.
- Statistik koleksi per platform dan tipe konten.
- Preprocessing wajib berupa deduplikasi dan normalisasi whitespace pada `content`.

## Struktur

```text
backend/
├── app/
│   ├── routers/       # HTTP routes
│   ├── schemas/       # Pydantic request/response models
│   └── services/      # Auth, scraping jobs, export
├── configs/           # Runtime paths and scraper settings
├── src/
│   ├── auth/          # Interactive login and session validation
│   ├── preprocessing/ # Required deduplication and whitespace normalization
│   ├── scraping/      # X, Threads, and shared browser utilities
│   └── pipeline/      # Scrape, normalize, statistics, export
├── storage/
│   ├── dictionaries/
│   ├── exports/
│   └── sessions/
├── tests/
├── main_api.py
├── main_cli.py
└── requirements.txt
```

## API

Server berjalan pada port `8080`.

| Endpoint | Method | Fungsi |
|---|---:|---|
| `/api/v1/health` | GET | Health check ringan |
| `/api/v1/auth/status` | GET | Status sesi X dan Threads |
| `/api/v1/auth/login-trigger/{platform}` | POST | Memulai login interaktif |
| `/api/v1/pipeline/run` | POST | Membuat background scraping job |
| `/api/v1/pipeline/status/{job_id}` | GET | Memeriksa status job |
| `/api/v1/pipeline/exports/{filename}` | GET | Mengunduh CSV hasil scraping |
| `/` | GET | Informasi service dan dokumentasi |

Swagger tersedia di `http://localhost:8080/docs`.

### Menjalankan scraping

```json
{
  "keywords": ["RUU Polri"],
  "direct_urls": [],
  "platform": "both",
  "search_mode": "latest",
  "max_links": 50,
  "max_scroll_steps": 300,
  "headless": false,
  "export_csv": true
}
```

Minimal satu `keywords` atau `direct_urls` harus diberikan.

Response awal berisi `job_id`. Gunakan job ID tersebut untuk polling endpoint
status sampai status menjadi `success` atau `error`.

## Format CSV

Kolom inti:

```text
platform
source
source_thread
user_id
type
date
content
```

Preprocessing wajib diterapkan sebelum statistik dan ekspor. Sistem melakukan
deduplikasi serta merapikan whitespace pada kolom `content`. URL, mention,
hashtag, angka, emoji, tanda baca, kapitalisasi, dan istilah slang tidak diubah.
Tidak ada kolom `clean_text`; CSV hanya menyimpan satu kolom teks `content`.

## Session login

Profile browser disimpan di:

```text
storage/sessions/x_profile/
storage/sessions/threads_profile/
```

Login interaktif dilakukan melalui browser native yang terbuka langsung di desktop.

## Instalasi lokal

Backend ditargetkan untuk **Python 3.15.2**. Rilis ini memuat perbaikan keamanan
untuk sertifikat intermediate eMudhra yang dikompromikan. Gunakan patch release
3.15 terbaru bila tersedia; jangan gunakan Python 3.10 yang sudah end-of-life.

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
playwright install chromium
uvicorn main_api:app --reload --host 0.0.0.0 --port 8080
```

CLI lokal:

```powershell
python main_cli.py
```

## Pengujian

```powershell
python -m unittest discover -s tests -v
python tests\check_pipeline_text_columns.py
```

## Dependensi

Dependensi utama: FastAPI, Pandas, Playwright, Parsel, Rich, tqdm, dan utilitas konfigurasi.
