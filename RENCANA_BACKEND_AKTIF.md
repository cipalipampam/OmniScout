# OmniScout - Rencana Backend Aktif

Dokumen ini adalah rencana kerja aktif untuk backend OmniScout per 2026-10-21.

Fokus saat ini adalah membuat proses penyaringan informasi dan pengelolaan account X/Threads berjalan proper menggunakan filesystem. Database dan frontend belum menjadi bagian dari pengerjaan aktif.

## 1. Status Scope

### Aktif sekarang

- Stabilitas pipeline scraping X dan Threads.
- Penyaringan, deduplikasi, normalisasi, checkpoint, dan export CSV.
- Job background dengan satu proses Uvicorn.
- Pengelolaan banyak account untuk setiap platform.
- Pemilihan account saat login dan scraping.
- Status validasi session per account.
- Lock agar satu browser profile tidak digunakan secara bersamaan.
- Test dan dokumentasi backend.

### Ditunda

- Frontend React/Vite/TypeScript.
- SQLite dan MySQL.
- Redis, Celery, ARQ, atau queue eksternal.
- Multi-worker Uvicorn.
- WebSocket real-time.
- Multi-user, role, dan permission.
- Deployment public/cloud.
- Object storage.
- Dashboard dan analitik lanjutan.

## 2. Kondisi Backend Saat Ini

### Storage yang dipertahankan

```text
backend/storage/
├── accounts/
│   └── accounts.json              # metadata account, bukan credential
├── sessions/
│   ├── x/
│   │   └── <account_id>/profile/  # browser profile account X
│   └── threads/
│       └── <account_id>/profile/  # browser profile account Threads
├── exports/                       # CSV dan checkpoint
└── dictionaries/                  # kamus preprocessing
```

Profile Chromium tetap berada di filesystem. Cookie, token, dan password tidak disalin ke `accounts.json` maupun file metadata lain.

### Batas runtime

- Satu proses Uvicorn.
- Tidak ada database.
- Job status masih disimpan oleh `JobManager` selama proses hidup.
- Scraping X dan Threads boleh berjalan bersamaan.
- Account yang sama tidak boleh dipakai oleh dua task browser bersamaan.
- Untuk tahap awal, satu platform dapat dibuat serial demi menjaga stabilitas profile dan rate limit.

## 3. Tujuan Account Management

User harus dapat:

1. Menambahkan account X baru.
2. Menambahkan account Threads baru.
3. Memberi nama account yang mudah dikenali.
4. Memilih account ketika memulai login.
5. Melihat status session setiap account.
6. Mengulangi login hanya untuk account tertentu.
7. Memilih account X dan/atau Threads untuk scraping.
8. Mengetahui account yang dipakai oleh sebuah job.
9. Menonaktifkan account tanpa menghapus profile.
10. Menghapus account setelah konfirmasi, dengan opsi mempertahankan atau menghapus profile.

## 4. Desain Registry Account Tanpa Database

Gunakan file metadata terpisah dari profile browser:

```text
backend/storage/accounts/accounts.json
```

Contoh struktur:

```json
{
  "accounts": [
    {
      "account_id": "x-personal",
      "platform": "x",
      "display_name": "X Personal",
      "profile_path": "storage/sessions/x/x-personal/profile",
      "enabled": true,
      "created_at": "2026-10-21T10:00:00+07:00",
      "updated_at": "2026-10-21T10:00:00+07:00"
    },
    {
      "account_id": "x-research",
      "platform": "x",
      "display_name": "X Research",
      "profile_path": "storage/sessions/x/x-research/profile",
      "enabled": true,
      "created_at": "2026-10-21T10:05:00+07:00",
      "updated_at": "2026-10-21T10:05:00+07:00"
    }
  ]
}
```

### Aturan registry

- `account_id` unik secara global atau unik per platform; rekomendasi: unik secara global.
- `account_id` hanya boleh berisi huruf kecil, angka, dash, dan underscore.
- `display_name` boleh berisi nama yang lebih ramah user.
- `platform` hanya `x` atau `threads`.
- `profile_path` dibentuk backend, bukan dikirim bebas dari request.
- `enabled=false` membuat account tidak dapat dipilih untuk login/scraping.
- Penulisan `accounts.json` harus atomic menggunakan temporary file lalu replace.
- Tambahkan lock file atau in-process lock ketika registry dibaca dan ditulis.
- Jika registry rusak, backend harus gagal dengan pesan yang jelas dan tidak menghapus profile.

### Kompatibilitas profile lama

Profile saat ini berada di:

```text
storage/sessions/x_profile/
storage/sessions/threads_profile/
```

Jangan langsung menghapusnya. Buat migration lokal satu kali:

```text
x_profile       -> x/x-default/profile
threads_profile -> threads/threads-default/profile
```

Account default diberi `account_id` yang stabil agar job dan konfigurasi lama tetap dapat dipakai.

## 5. API Account yang Dibutuhkan

### Daftar account

```text
GET /api/v1/accounts
```

Query opsional:

```text
GET /api/v1/accounts?platform=x&enabled_only=true
```

Response minimal:

```json
{
  "accounts": [
    {
      "account_id": "x-personal",
      "platform": "x",
      "display_name": "X Personal",
      "enabled": true,
      "profile_path": "x/x-personal/profile",
      "is_valid": true,
      "message": "Sesi X ditemukan dan masih aktif."
    }
  ]
}
```

### Tambah account

```text
POST /api/v1/accounts
```

Request:

```json
{
  "platform": "x",
  "display_name": "X Research"
}
```

Backend membuat `account_id`, folder profile, dan metadata registry. Credential tetap dimasukkan melalui browser login interaktif, bukan request API.

### Detail account

```text
GET /api/v1/accounts/{account_id}
```

### Update account

```text
PATCH /api/v1/accounts/{account_id}
```

Perubahan yang diizinkan pada tahap awal:

- `display_name`.
- `enabled`.

Platform dan `account_id` tidak diubah setelah account dibuat.

### Hapus account

```text
DELETE /api/v1/accounts/{account_id}?delete_profile=false
```

Default `delete_profile=false` agar metadata dapat dihapus tanpa menghancurkan session. Penghapusan profile harus eksplisit dan tervalidasi.

### Login account

Perlu mengganti endpoint saat ini dari:

```text
POST /api/v1/auth/login-trigger/{platform}
```

menjadi:

```text
POST /api/v1/auth/login-trigger/{platform}/{account_id}
```

Endpoint lama dapat dipertahankan sementara sebagai alias ke account default.

### Status session

Endpoint global:

```text
GET /api/v1/auth/status
```

Endpoint account:

```text
GET /api/v1/auth/status/{account_id}
```

Status global harus berisi daftar account, bukan hanya satu status per platform.

## 6. Perubahan Request Scraping

Request scraping perlu memilih account secara eksplisit:

```json
{
  "keywords": ["RUU Polri"],
  "direct_urls": [],
  "platform": "both",
  "account_ids": {
    "x": "x-research",
    "threads": "threads-research"
  },
  "search_mode": "latest",
  "max_links": 50,
  "max_scroll_steps": 300,
  "headless": false,
  "export_csv": true
}
```

### Aturan pemilihan account

- Platform `x` wajib memiliki `account_ids.x`.
- Platform `threads` wajib memiliki `account_ids.threads`.
- Platform `both` wajib memiliki account untuk kedua platform.
- Account harus terdaftar, enabled, dan platform-nya sesuai.
- Account yang session-nya invalid ditolak sebelum browser scraping dimulai.
- `account_ids` tidak boleh diterima sebagai path filesystem.
- Job menyimpan account yang digunakan pada metadata job dan nama export.

Untuk kompatibilitas sementara, jika `account_ids` kosong dan hanya ada satu account aktif pada platform tersebut, backend boleh memilih account itu secara otomatis. Jika terdapat lebih dari satu account aktif, request harus meminta pilihan eksplisit.

## 7. Lock dan Concurrency

Lock saat ini bersifat per platform. Dengan banyak account, target aman tahap awal adalah lock per `account_id`:

```text
lock:x:x-personal
lock:x:x-research
lock:threads:threads-personal
lock:threads:threads-research
```

Aturan:

- Account yang sama tidak boleh login dan scraping bersamaan.
- X Personal dan X Research dapat diproses paralel hanya setelah test stabil.
- X dan Threads dapat berjalan bersamaan.
- Jangan membuka dua Playwright context untuk profile yang sama.
- Status lock harus terlihat di log tanpa mencetak credential.
- Jika account sedang digunakan, request baru mendapatkan error terkontrol atau masuk antrean memory sederhana.

Implementasi awal yang disarankan: gunakan lock per account tetapi tetap batasi satu job aktif per platform sampai pengujian concurrency selesai.

## 8. Struktur Service Backend

```text
backend/
├── app/
│   ├── routers/
│   │   ├── api_accounts.py
│   │   ├── api_auth.py
│   │   └── api_pipeline.py
│   ├── schemas/
│   │   ├── account_schema.py
│   │   ├── auth_schema.py
│   │   └── scrape_schema.py
│   └── services/
│       ├── account_service.py
│       ├── auth_service.py
│       ├── job_service.py
│       └── pipeline_service.py
├── configs/
│   └── config.py
├── src/
│   ├── auth/
│   │   └── session_manager.py
│   └── scraping/
└── storage/
    ├── accounts/accounts.json
    └── sessions/{platform}/{account_id}/profile/
```

## 9. Alur Logic Account

### Menambahkan account

1. Validasi platform dan display name.
2. Generate `account_id` yang aman dan unik.
3. Buat folder profile account.
4. Tulis metadata ke registry secara atomic.
5. Kembalikan account dengan status belum login.

### Login account

1. Validasi account aktif dan platform sesuai.
2. Ambil profile path dari registry.
3. Ambil lock account.
4. Buka Playwright headed dengan profile tersebut.
5. User menyelesaikan login pada browser native/noVNC.
6. Tutup browser setelah proses login selesai.
7. Validasi cookie dan host platform.
8. Kembalikan status valid atau pesan kegagalan.

### Validasi session

1. Baca registry account.
2. Untuk setiap account aktif, resolve profile path dari metadata internal.
3. Cek folder profile.
4. Salin database cookie ke temporary file seperti mekanisme saat ini.
5. Validasi cookie wajib, expiry, dan host.
6. Kembalikan status per account.

### Menjalankan scraping

1. Validasi keyword atau direct URL.
2. Validasi account berdasarkan platform.
3. Validasi session account.
4. Buat job dan simpan account ID pada metadata memory.
5. Ambil lock account.
6. Jalankan scraper dengan profile account terpilih.
7. Tulis checkpoint/export dengan job ID dan account ID.
8. Lepaskan lock pada `finally`.
9. Kembalikan status success/error.

## 10. Penamaan File dan Checkpoint

Gunakan nama yang memuat job ID, platform, dan account ID agar tidak tertukar:

```text
{timestamp}_{job_id}_{platform}_{account_id}_checkpoint.csv
{timestamp}_{job_id}_{platform}_{account_id}_result.csv
```

Jika account ID mengandung karakter yang tidak aman, gunakan slug yang dibuat backend. Jangan gunakan display name mentah pada path file.

## 11. Phase Pengerjaan Aktif

Checklist berikut adalah scope yang dikerjakan sekarang.

### Phase A - Baseline dan kontrak account

**Estimasi:** 1 hari

- [ ] Jalankan semua test backend existing.
- [ ] Catat alur auth dan scraping saat ini.
- [ ] Tetapkan bentuk `accounts.json`.
- [ ] Tetapkan aturan account ID dan path.
- [ ] Tetapkan kompatibilitas `x_profile` dan `threads_profile`.
- [ ] Tambahkan test untuk account ID invalid dan account platform mismatch.

**Gate:** kontrak account dan aturan migrasi profile disepakati.

### Phase B - Account registry service

**Estimasi:** 1-2 hari

- [ ] Buat `account_schema.py`.
- [ ] Buat `account_service.py`.
- [ ] Implementasikan read registry.
- [ ] Implementasikan write atomic.
- [ ] Implementasikan create account.
- [ ] Implementasikan update display name/enabled.
- [ ] Implementasikan delete metadata.
- [ ] Buat folder profile otomatis.
- [ ] Tambahkan test registry kosong, duplikasi, dan file rusak.

**Gate:** account dapat dibuat, dibaca, diubah, dan dinonaktifkan tanpa database.

### Phase C - Migrasi profile tunggal

**Estimasi:** 1 hari

- [ ] Deteksi profile lama.
- [ ] Buat account default X.
- [ ] Buat account default Threads.
- [ ] Pindahkan atau gunakan compatibility mapping secara aman.
- [ ] Jangan menghapus folder lama otomatis tanpa backup.
- [ ] Tambahkan test path profile.

**Gate:** session lama tetap terdeteksi setelah struktur multi-account aktif.

### Phase D - Multi-account session manager

**Estimasi:** 2-3 hari

- [ ] Ubah `PLATFORM_PROFILES` menjadi resolver berdasarkan account ID.
- [ ] Validasi cookie berdasarkan profile account.
- [ ] Ubah status global menjadi daftar account.
- [ ] Tambahkan status detail account.
- [ ] Ubah login task agar menerima `account_id`.
- [ ] Terapkan lock per account.
- [ ] Pastikan profile path tidak berasal langsung dari input request.
- [ ] Tambahkan test dua account pada platform yang sama.

**Gate:** dua account X dapat memiliki status session berbeda dan tidak saling memakai profile.

### Phase E - API account dan auth

**Estimasi:** 2 hari

- [ ] Buat router account.
- [ ] Buat endpoint list, detail, create, patch, delete.
- [ ] Tambahkan endpoint login account.
- [ ] Tambahkan endpoint status account.
- [ ] Pertahankan alias endpoint lama untuk default account.
- [ ] Tambahkan response error 404, 409, dan 422 yang konsisten.
- [ ] Perbarui Swagger description.
- [ ] Tambahkan test endpoint.

**Gate:** account dapat dikelola dan login melalui API tanpa menyentuh path manual.

### Phase F - Integrasi account ke pipeline

**Estimasi:** 2-3 hari

- [ ] Tambahkan `account_ids` ke schema scraping.
- [ ] Validasi account terhadap platform.
- [ ] Tolak account disabled atau session invalid.
- [ ] Simpan account ID pada job record memory.
- [ ] Pass profile account ke scraper.
- [ ] Tambahkan account ID pada checkpoint/export filename.
- [ ] Pastikan lock dilepas ketika error.
- [ ] Tambahkan test platform x, threads, dan both.

**Gate:** job scraping menggunakan account yang dipilih dan hasilnya dapat dilacak ke account tersebut.

### Phase G - Penyaringan informasi dan reliability

**Estimasi:** 3-5 hari

- [ ] Verifikasi deduplikasi lintas checkpoint.
- [ ] Verifikasi normalisasi whitespace.
- [ ] Verifikasi filter teks sistem.
- [ ] Verifikasi resume setelah proses terhenti.
- [ ] Verifikasi file checkpoint tidak tertimpa antar account.
- [ ] Verifikasi hasil X dan Threads dalam mode both.
- [ ] Tambahkan logging account ID tanpa credential.
- [ ] Tambahkan test partial failure satu platform.
- [ ] Tambahkan validasi output CSV.

**Gate:** proses penyaringan menghasilkan output konsisten dan dapat dilanjutkan dengan aman.

### Phase H - Hardening backend

**Estimasi:** 2-3 hari

- [ ] Rapikan error response.
- [ ] Perketat CORS untuk environment lokal yang dipakai.
- [ ] Tambahkan timeout dan cleanup task.
- [ ] Pastikan account registry tidak rusak ketika proses berhenti saat write.
- [ ] Uji login dan scraping bergantian pada account sama.
- [ ] Uji X dan Threads bersamaan.
- [ ] Uji dua account berbeda.
- [ ] Perbarui README backend.
- [ ] Perbarui checklist operasional.

**Gate:** backend siap menjadi fondasi sebelum frontend dikerjakan.

## 12. Phase Ditunda

### Ditunda 1 - Frontend

Status: **Ditunda**.

Scope nantinya:

- React + Vite + TypeScript.
- Halaman daftar account.
- Form tambah account.
- Tombol login per account.
- Selector account pada form scraping.
- Monitor job dan download CSV.

### Ditunda 2 - Database

Status: **Ditunda**.

Untuk kebutuhan saat ini tidak ada SQLite/MySQL. Jika nanti diperlukan history lintas restart, mulai dari SQLite untuk metadata job dan account. CSV, checkpoint, dan browser profile tetap dapat berada di filesystem.

### Ditunda 3 - Queue dan scaling

Status: **Ditunda**.

Redis, Celery/ARQ, multi-worker, dan parallel job dalam jumlah besar hanya dikerjakan jika kebutuhan runtime berubah.

## 13. Definition of Done Backend Saat Ini

- [ ] Account X lebih dari satu dapat dibuat dan disimpan di registry.
- [ ] Account Threads lebih dari satu dapat dibuat dan disimpan di registry.
- [ ] Setiap account memiliki profile browser terpisah.
- [ ] Status session ditampilkan per account.
- [ ] Login dapat ditargetkan ke account tertentu.
- [ ] Scraping dapat memilih account untuk setiap platform.
- [ ] Account disabled atau invalid tidak dapat dipakai scraping.
- [ ] Profile yang sama tidak digunakan dua task bersamaan.
- [ ] X dan Threads dapat diproses bersamaan.
- [ ] Checkpoint dan CSV tidak saling tertimpa.
- [ ] Pipeline filter, deduplikasi, dan normalisasi tetap lulus test.
- [ ] Session lama tetap kompatibel atau berhasil dimigrasikan.
- [ ] Semua test backend aktif lulus.
- [ ] Frontend, database, dan queue tetap berstatus Ditunda.

## 14. Urutan Pengerjaan Terdekat

1. Finalisasi desain `accounts.json`.
2. Implementasikan account registry service.
3. Migrasikan profile lama menjadi account default.
4. Ubah session manager agar menerima account ID.
5. Ubah login endpoint dan status endpoint.
6. Tambahkan account ID pada request pipeline.
7. Uji dua account X dan dua account Threads.
8. Uji scraping X dan Threads secara bersamaan.
9. Perbaiki checkpoint/export agar account-safe.
10. Jalankan regression test backend.
