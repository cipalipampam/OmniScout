# OmniScout - Rencana Pengembangan

Dokumen ini menjadi acuan implementasi frontend dan database OmniScout berdasarkan kondisi repository pada 2026-10-20.

## 1. Keputusan Teknologi

### Backend

- FastAPI tetap menjadi REST API utama pada port `8080` dengan prefix `/api/v1`.
- Pipeline scraping, Playwright, lock per platform, dan browser session tetap dipakai.
- Job scraping tetap asynchronous; frontend melakukan polling status job.

### Frontend

- React, Vite, dan TypeScript.
- TanStack Query untuk request, cache, dan polling.
- React Hook Form + Zod untuk validasi form.
- Tailwind CSS untuk styling.
- Recharts untuk grafik statistik.
- Lucide React untuk icon.

### Database

- MySQL 8.0+.
- SQLAlchemy 2.x sebagai ORM.
- Alembic untuk migration.
- PyMySQL sebagai driver awal karena setup Windows lebih sederhana.

### Storage

- CSV tetap di `backend/storage/exports/`.
- Browser profile tetap di `backend/storage/sessions/` atau Docker volume.
- MySQL menyimpan metadata job, hasil scraping, dan metadata export.
- Cookie, password, token, dan seluruh profile Chromium tidak disimpan di MySQL.

### Di luar MVP

- Redis dan Celery/ARQ belum wajib.
- Multi-user dan role management belum menjadi blocker MVP.
- Deployment cloud dan object storage dikerjakan setelah alur lokal stabil.

## 2. Tujuan Produk

OmniScout harus memungkinkan user untuk:

1. Memeriksa kesiapan session X dan Threads.
2. Memulai scraping berdasarkan keyword atau URL langsung.
3. Memantau job scraping background.
4. Melihat jumlah data, user unik, sumber, platform, dan tipe konten.
5. Melihat preview hasil scraping.
6. Mengunduh hasil dalam format CSV.
7. Menyimpan riwayat proses setelah backend restart.

## 3. Scope MVP

### Fitur wajib

- Dashboard ringkasan dan health check backend.
- Status session X dan Threads.
- Trigger login tiap platform.
- Form scraping dengan keyword atau direct URL.
- Pilihan platform, search mode, max links, max scroll, headless, dan export CSV.
- Polling status job: queued, running, success, error.
- Progress message dan statistik hasil.
- Riwayat job dan detail job.
- Preview hasil dengan pagination.
- Download CSV.
- Loading, empty, error, retry, dan responsive state.
- Persistence job dan hasil penting ke MySQL.

### Non-goal MVP

- Editing atau penghapusan posting.
- Sentiment analysis atau klasifikasi lanjutan.
- WebSocket real-time.
- Banyak akun sosial media per platform.
- Role dan permission kompleks.
- Penyimpanan password atau cookie mentah.

## 4. Requirement Fungsional

### FR-01 Health check

Gunakan `GET /api/v1/health`.

- Tampilkan online jika response sukses.
- Tampilkan offline jika timeout atau gagal.
- Sediakan tombol retry.

### FR-02 Status session

Gunakan `GET /api/v1/auth/status` untuk menampilkan:

- Status session X.
- Status session Threads.
- `all_valid`.
- Mode login: native, noVNC, atau unavailable.
- Pesan dari backend.

Tombol login ditampilkan untuk platform yang belum valid. Jika mode `novnc`, tampilkan link noVNC.

### FR-03 Trigger login

Gunakan `POST /api/v1/auth/login-trigger/{platform}`.

- Disable tombol selama request.
- Tampilkan pesan response.
- Informasikan apakah browser native atau noVNC harus digunakan.
- Sediakan refresh status setelah user selesai login.

### FR-04 Membuat scraping job

| Field | Tipe | Aturan |
|---|---|---|
| `keywords` | array string | Boleh kosong jika ada direct URL |
| `direct_urls` | array string | Boleh kosong jika ada keyword |
| `platform` | enum | `x`, `threads`, `both` |
| `search_mode` | enum | `latest`, `top` |
| `max_links` | integer | 1 sampai 500 |
| `max_scroll_steps` | integer | 50 sampai 5000 |
| `headless` | boolean | Default false |
| `export_csv` | boolean | Default true |

Frontend harus menolak keyword dan URL yang sama-sama kosong, membuang item kosong, dan mengikuti batas validasi backend. Response `202` menyimpan `job_id` lalu membuka detail job.

### FR-05 Monitoring job

Gunakan `GET /api/v1/pipeline/status/{job_id}`.

- Polling setiap 2 detik ketika status queued/running.
- Berhenti pada success/error.
- Retry error jaringan maksimal tiga kali.
- Tampilkan pesan progress terakhir.

### FR-06 Statistik

Saat sukses, tampilkan total data, user unik, source unik, durasi, breakdown platform, dan breakdown tipe konten. Gunakan kartu ringkas dan grafik sederhana.

### FR-07 Riwayat job

Tampilkan ID, waktu, platform, keyword, status, total data, durasi, link detail, dan link download. Backend saat ini menyimpan job di memory sehingga endpoint history dan persistence MySQL harus ditambahkan.

### FR-08 Preview dan export

Preview minimal berisi platform, tipe konten, user ID, tanggal, content, dan source URL. Preview wajib memiliki pagination, loading, empty, dan error state. Download hanya aktif jika `exported_file` tersedia dan filename berasal dari backend.

## 5. Requirement Non-Fungsional

- Polling berhenti otomatis saat job selesai.
- Dataset besar menggunakan batch insert dan pagination.
- Job tetap terbaca setelah backend restart.
- CORS wildcard hanya untuk development; production memakai origin eksplisit.
- Database credential hanya berasal dari environment variable.
- Token, cookie, dan credential tidak boleh masuk log.
- Schema hanya diubah melalui Alembic migration.
- Semua response API memiliki type TypeScript.
- Scraping tetap menggunakan platform lock.

## 6. Arsitektur Target

```text
React/Vite/TypeScript
        | HTTP REST + polling
        v
FastAPI
  |                 |
  |                 +--> MySQL: runs, posts, exports metadata
  |
  +--> Scraping pipeline
          |--> Playwright X
          |--> Playwright Threads
          |--> Browser profiles on filesystem/volume
          +--> CSV exports on filesystem/volume
```

## 7. Struktur Frontend

```text
frontend/
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   ├── router.tsx
│   │   └── query-client.ts
│   ├── components/
│   │   ├── ui/
│   │   ├── layout/
│   │   ├── StatusBadge.tsx
│   │   ├── LoadingState.tsx
│   │   └── ErrorState.tsx
│   ├── features/
│   │   ├── dashboard/
│   │   ├── auth-session/
│   │   ├── scrape-job/
│   │   ├── job-history/
│   │   └── results/
│   ├── lib/
│   │   ├── api-client.ts
│   │   ├── formatters.ts
│   │   └── validators.ts
│   ├── types/api.ts
│   └── main.tsx
├── .env.example
├── package.json
└── vite.config.ts
```

Halaman yang dibuat: `/` dashboard, `/scrape/new` form baru, `/jobs` riwayat, `/jobs/:jobId` detail, dan `/sessions` pengelolaan session.

## 8. Desain Database MySQL

Gunakan UUID eksternal, timestamp UTC, foreign key, dan index. Data normalisasi tetap mengikuti pipeline saat ini: filter, deduplikasi, dan normalisasi whitespace pada `content`.

### `scrape_runs`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | CHAR(36) | Primary key |
| `status` | VARCHAR(20) | queued/running/success/error |
| `platform` | VARCHAR(20) | x/threads/both |
| `search_mode` | VARCHAR(20) | latest/top |
| `max_links` | INT | Konfigurasi job |
| `max_scroll_steps` | INT | Konfigurasi job |
| `headless` | BOOLEAN | Konfigurasi job |
| `export_csv` | BOOLEAN | Konfigurasi job |
| `message` | TEXT | Status terakhir |
| `total_data` | INT | Total hasil |
| `elapsed_seconds` | DECIMAL(10,2) | Durasi |
| `error_detail` | TEXT NULL | Detail error |
| `exported_file` | VARCHAR(255) NULL | Nama file |
| `created_at` | DATETIME | Waktu dibuat |
| `started_at` | DATETIME NULL | Waktu mulai |
| `completed_at` | DATETIME NULL | Waktu selesai |

### `scrape_keywords`

`id BIGINT`, `scrape_run_id CHAR(36)`, `keyword VARCHAR(255)`, dan `created_at DATETIME`.

### `scrape_urls`

`id BIGINT`, `scrape_run_id CHAR(36)`, `url TEXT`, dan `created_at DATETIME`.

### `scraped_posts`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | BIGINT | Primary key |
| `scrape_run_id` | CHAR(36) | Foreign key |
| `platform` | VARCHAR(20) | x/threads |
| `source` | VARCHAR(500) NULL | Source |
| `source_thread` | VARCHAR(500) NULL | Parent thread |
| `user_id` | VARCHAR(255) NULL | User atau username |
| `content_type` | VARCHAR(30) NULL | post/comment |
| `posted_at` | DATETIME NULL | Waktu posting |
| `content` | TEXT | Teks hasil preprocessing |
| `content_hash` | CHAR(64) | Hash deduplikasi |
| `raw_data` | JSON NULL | Metadata aman |
| `created_at` | DATETIME | Waktu disimpan |

### `export_files`

`id BIGINT`, `scrape_run_id CHAR(36)`, `filename VARCHAR(255)`, `storage_path VARCHAR(500)`, `row_count INT`, dan `created_at DATETIME`.

Index minimum: `scrape_runs.status`, `scrape_runs.created_at`, `scraped_posts.scrape_run_id`, `scraped_posts.platform`, `scraped_posts.content_hash`, dan `scraped_posts.posted_at`.

## 9. Perubahan API Backend

### Endpoint existing

| Endpoint | Penggunaan |
|---|---|
| `GET /api/v1/health` | Status backend |
| `GET /api/v1/auth/status` | Status session |
| `POST /api/v1/auth/login-trigger/{platform}` | Trigger login |
| `POST /api/v1/pipeline/run` | Buat job |
| `GET /api/v1/pipeline/status/{job_id}` | Polling |
| `GET /api/v1/pipeline/exports/{filename}` | Download CSV |

### Endpoint baru

| Endpoint | Tujuan |
|---|---|
| `GET /api/v1/pipeline/jobs` | History dengan filter dan pagination |
| `GET /api/v1/pipeline/jobs/{job_id}/results` | Preview hasil pagination |
| `GET /api/v1/pipeline/jobs/{job_id}/statistics` | Statistik tersimpan |
| `DELETE /api/v1/pipeline/jobs/{job_id}` | Opsional, hapus metadata dan hasil |

Kontrak endpoint existing dipertahankan. Persistence dipindahkan ke service/database tanpa perubahan tidak perlu pada frontend.

## 10. Alur Logic

### Membuka dashboard

1. Baca `VITE_API_BASE_URL`.
2. Panggil health check.
3. Panggil status session.
4. Ambil job terbaru.
5. Tampilkan loading lalu data, atau error dengan retry.

### Login platform

1. Buka Sessions dan baca status.
2. User menekan Login X atau Threads.
3. Frontend mengirim trigger.
4. Backend menjalankan browser login background.
5. UI menampilkan instruksi native/noVNC.
6. User menyelesaikan login dan menekan refresh.

### Membuat dan memantau scraping

1. User mengisi keyword atau URL.
2. Frontend membersihkan whitespace dan validasi.
3. Frontend mengirim `POST /pipeline/run`.
4. Backend membuat `scrape_runs` berstatus queued.
5. Backend menjalankan pipeline.
6. Frontend menerima `job_id` dan membuka detail.
7. Frontend polling status setiap dua detik.
8. Polling berhenti pada success/error.
9. Success menampilkan statistik, hasil, dan export; error menampilkan pesan retry.

### Menyimpan hasil

1. Scraper mengumpulkan data.
2. Pipeline melakukan filter, deduplikasi, dan normalisasi whitespace.
3. Backend menghitung `content_hash`.
4. Backend batch insert ke `scraped_posts`.
5. Jika aktif, backend membuat CSV dan menyimpan `export_files`.
6. Backend mengubah run menjadi success.

## 11. Jadwal Phase dan Tracker

Estimasi total: 8 minggu, 5 hari kerja per minggu. Ubah `[ ]` menjadi `[x]` setelah acceptance gate fase terpenuhi.

### Phase 0 - Baseline dan persiapan

**Durasi:** Hari 1-2

- [ ] Jalankan backend port 8080.
- [ ] Verifikasi health, auth status, dan pipeline melalui Swagger.
- [ ] Jalankan test backend yang tersedia.
- [ ] Tentukan versi Node.js, npm, dan MySQL.
- [ ] Buat `.env.example` frontend/backend.

**Output:** environment dan baseline terverifikasi.

**Gate:** endpoint utama dapat diuji tanpa error environment.

### Phase 1 - Bootstrap frontend

**Durasi:** Hari 3-5

- [ ] Buat Vite React TypeScript di `frontend`.
- [ ] Tambahkan router, TanStack Query, Tailwind, lint, dan formatter.
- [ ] Buat API client terpusat.
- [ ] Buat type TypeScript untuk API existing.
- [ ] Buat layout, loading, error, empty state, badge, dan button.

**Output:** frontend shell berjalan.

**Gate:** `npm run build` sukses dan health check tampil.

### Phase 2 - Dashboard dan session

**Durasi:** Minggu 2

- [ ] Dashboard summary.
- [ ] Health indicator.
- [ ] Status X dan Threads.
- [ ] Halaman Sessions.
- [ ] Trigger login tiap platform.
- [ ] Tampilan native/noVNC/unavailable.
- [ ] Refresh manual, timeout, dan retry.

**Gate:** status session dan login trigger terverifikasi lokal.

### Phase 3 - Form scraping

**Durasi:** Minggu 3

- [ ] Halaman `/scrape/new`.
- [ ] Input keyword dan direct URL dinamis.
- [ ] Selector platform dan search mode.
- [ ] Input max links dan max scroll.
- [ ] Toggle headless dan export CSV.
- [ ] Validasi Zod dan mapping error Pydantic.
- [ ] Submit API dan redirect berdasarkan `job_id`.

**Gate:** input valid, batas angka, dan error API tertangani.

### Phase 4 - Monitoring dan hasil

**Durasi:** Minggu 4

- [ ] Halaman `/jobs/:jobId`.
- [ ] Polling queued/running.
- [ ] Tampilan success/error.
- [ ] Progress message dan durasi.
- [ ] Statistik total, user, source, platform, tipe.
- [ ] Chart Recharts.
- [ ] Tombol download CSV.
- [ ] Stop polling pada terminal state.

**Gate:** satu scraping berhasil dari form sampai download CSV.

### Phase 5 - Schema MySQL

**Durasi:** Minggu 5

- [ ] Tambahkan SQLAlchemy, PyMySQL, dan Alembic.
- [ ] Tambahkan `DATABASE_URL`.
- [ ] Buat model `scrape_runs`.
- [ ] Buat model `scrape_keywords`.
- [ ] Buat model `scrape_urls`.
- [ ] Buat model `scraped_posts`.
- [ ] Buat model `export_files`.
- [ ] Buat migration awal, foreign key, dan index.
- [ ] Tambahkan test koneksi database.

**Gate:** database kosong dapat dibuat ulang melalui migration saja.

### Phase 6 - Persistence dan API history

**Durasi:** Minggu 6

- [ ] Simpan job baru ke `scrape_runs`.
- [ ] Update queued/running/success/error ke database.
- [ ] Simpan keyword dan URL input.
- [ ] Batch insert hasil ke `scraped_posts`.
- [ ] Simpan metadata export.
- [ ] Buat endpoint list jobs.
- [ ] Buat endpoint results pagination.
- [ ] Buat endpoint statistics.
- [ ] Baca status utama dari database.
- [ ] Uji status setelah restart backend.

**Gate:** job dan hasil tetap tersedia setelah restart.

### Phase 7 - History, preview, dan UX

**Durasi:** Minggu 7

- [ ] Halaman `/jobs`.
- [ ] Filter status, platform, dan tanggal.
- [ ] Pagination history.
- [ ] Preview hasil dari database.
- [ ] Pagination tabel data.
- [ ] Expand content panjang.
- [ ] Empty state dan error state.
- [ ] Responsive mobile.
- [ ] Keyboard navigation dasar.

**Gate:** user dapat mencari job lama dan membuka hasil tanpa membaca CSV manual.

### Phase 8 - Hardening dan release candidate

**Durasi:** Minggu 8

- [ ] Test form dan API client.
- [ ] Test polling success/error.
- [ ] Test session retry.
- [ ] Test MySQL integration.
- [ ] Test duplicate content.
- [ ] Test path traversal download.
- [ ] Test backend restart.
- [ ] Test concurrent jobs berbeda platform.
- [ ] Perketat CORS.
- [ ] Pastikan secret tidak masuk repository.
- [ ] Perbarui README setup.
- [ ] Buat backup/restore procedure MySQL.

**Gate:** test lulus dan setup baru dapat dilakukan dari dokumentasi.

## 12. Milestone Tracking

| Milestone | Target | Status |
|---|---|---|
| M0 Baseline backend | Akhir Hari 2 | Belum mulai |
| M1 Frontend shell | Akhir Hari 5 | Belum mulai |
| M2 Session dashboard | Akhir Minggu 2 | Belum mulai |
| M3 Scraping form | Akhir Minggu 3 | Belum mulai |
| M4 End-to-end scraping UI | Akhir Minggu 4 | Belum mulai |
| M5 MySQL schema | Akhir Minggu 5 | Belum mulai |
| M6 Persistent jobs | Akhir Minggu 6 | Belum mulai |
| M7 History and preview | Akhir Minggu 7 | Belum mulai |
| M8 Release candidate | Akhir Minggu 8 | Belum mulai |

Status yang digunakan: `Belum mulai`, `Berjalan`, `Blocked`, dan `Selesai`.

## 13. Definition of Done MVP

- [ ] Frontend React/Vite/TypeScript berjalan.
- [ ] Health backend, status session, dan trigger login tersedia.
- [ ] User dapat membuat dan memantau scraping job.
- [ ] Statistik dan download CSV tersedia.
- [ ] Job dan hasil penting tersimpan di MySQL.
- [ ] History dan preview hasil tersedia.
- [ ] Job tetap terbaca setelah backend restart.
- [ ] Migration dapat dijalankan dari database kosong.
- [ ] Validasi, loading, empty, dan error state tersedia.
- [ ] Test utama lulus.
- [ ] Setup lokal terdokumentasi.

## 14. Risiko dan Mitigasi

| Risiko | Mitigasi |
|---|---|
| Session browser invalid | Tampilkan status session dan trigger login dari UI |
| Job hilang saat restart | Persist job ke MySQL |
| Scraping lama | Background job dan polling |
| Dataset besar | Batch insert, index, dan pagination |
| Profile browser dipakai bersamaan | Pertahankan platform lock |
| CSV tidak tersedia | Simpan metadata export dan validasi path |
| CORS terlalu terbuka | Restrict origin production |
| Schema berbeda antar environment | Wajib gunakan Alembic migration |
| Belum familiar MySQL | Gunakan Docker Compose atau panduan setup lokal |

## 15. Langkah Pertama

1. Pastikan Node.js, npm, dan MySQL tersedia.
2. Jalankan baseline backend dan test yang ada.
3. Buat project React/Vite/TypeScript di `frontend`.
4. Implementasikan health check dan API client.
5. Setelah frontend shell lulus build, lanjut ke status session.
