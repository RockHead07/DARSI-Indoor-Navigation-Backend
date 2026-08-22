# Panduan Setup Backend Docker & Ingress Cloudflare Tunnel (ADR-027)

Dokumen ini memandu proses deployment backend DARSI (FastAPI + PostgreSQL pgvector) menggunakan **Docker Compose** dan menghubungkannya ke internet publik menggunakan **Cloudflare Tunnel (`cloudflared`)**.

Pendekatan ini dirancang khusus untuk server privat/cloud yang berada di balik firewall atau OpenVPN agar dapat diakses oleh HP Android dan Unity tanpa membuka port *inbound* dan tanpa mewajibkan klien memasang VPN.

---

## 1. Menjalankan Backend dengan Docker Compose

### Langkah 1: Klon / Update Repo di Server
```bash
git clone https://github.com/RockHead07/DARSI-Indoor-Navigation-Backend.git darsi-backend
cd darsi-backend
```

### Langkah 2: Buat File `.env`
Salin template konfigurasi:
```bash
cp .env.docker.example .env
```
Edit file `.env` (misalnya dengan `nano .env`), pastikan mengisi `GROQ_API_KEY`:
```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=darsi
POSTGRES_DB=darsi
DB_PORT=5433

API_PORT=8000
POI_SYNC_TOKEN=darsi-admin-token
CORS_ORIGINS=*

GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

### Langkah 3: Jalankan Container
```bash
docker compose up -d --build
```
Perintah ini akan:
1. Membangun container `darsi-api` (FastAPI + FastEmbed ONNX).
2. Menjalankan database `darsi-db` (`pgvector/pgvector:pg16`).
3. Menginisialisasi skema tabel `pois`, `knowledge_chunks`, dan `doctor_schedules` secara otomatis dari file SQL.

### Langkah 4: Ingest Data Corpus Simulasi
Jalankan perintah ini sekali untuk memasukkan data pengetahuan dan jadwal dokter ke database:
```bash
docker compose exec api python -m scripts.ingest_corpus
```
*Output sukses: `Chunks: 25, Schedules: 4`.*

---

## 2. Menghubungkan ke Cloudflare Tunnel (Ingress)

Di server Anda, jalankan skrip pembantu:
```bash
chmod +x scripts/setup_cloudflare_tunnel.sh
./scripts/setup_cloudflare_tunnel.sh
```

Atau lakukan setup manual di bawah ini:

### Opsi A: Quick Tunnel (Pengujian Instan Tanpa Domain)
Cocok untuk langsung menguji dari Unity/HP dalam 1 menit:
```bash
cloudflared tunnel --url http://localhost:8000
```
Cloudflare akan menampilkan URL publik acak seperti:
`https://random-subdomain-1234.trycloudflare.com`

Salin URL tersebut dan masukkan ke Unity.

---

### Opsi B: Production Tunnel dengan Cloudflare Dashboard (Sangat Direkomendasikan ⭐)
Jika Anda memiliki akun Cloudflare (gratis) dan domain sendiri:

1. Buka [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com/) > **Networks** > **Tunnels**.
2. Klik **Add a Tunnel** > Pilih **Cloudflare Tunnel (cloudflared)**.
3. Beri nama tunnel (contoh: `darsi-backend-prod`).
4. Ikuti instruksi di layar untuk menginstal konektor di Linux (Cloudflare akan memberikan perintah satu baris seperti `sudo cloudflared service install eyJh...`).
5. Pada tab **Public Hostname**:
   * **Subdomain:** `api` (atau `darsi-api`)
   * **Domain:** domain Anda (contoh: `darsi.id` atau domain gratis)
   * **Type:** `HTTP`
   * **URL:** `localhost:8000`
6. Klik **Save Tunnel**.

Hasilnya, backend Anda sekarang memiliki URL HTTPS resmi permanen:
`https://api.domainanda.com`

---

## 3. Menghubungkan Klien Unity

1. Buka project Unity `DARSI-Indoor Navigation`.
2. Di scene `TestingHCM`, pilih GameObject `AssistantClient` (atau komponen `AssistantClient` pada Canvas).
3. Di Inspector, ubah **Base Url**:
   * Jika menggunakan Quick Tunnel: `https://random-subdomain-1234.trycloudflare.com`
   * Jika menggunakan Production Domain: `https://api.domainanda.com`
4. Tekan Play di Editor atau Build APK ke HP Android.
5. Lakukan pengujian tanya jawab:
   * 5× tap logo DARSI untuk membuka `AssistantTestPanel`.
   * Ketik pertanyaan (contoh: *"dokter anak ada hari apa"* atau *"farmasi di mana"*).
   * Tekan tombol **Tanya**.
