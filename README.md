# QuantLab

<h4>Demo Video: <href>https://lnkd.in/p/g-qU-rc7</href></h4>

QuantLab adalah proyek analisa saham Indonesia yang berawal dari proses belajar di mata kuliah Pasar Modal. Materi dan arahan dosen menjadi titik awal untuk memahami bagaimana membaca pasar, menghitung return, dan menilai risiko.

Dari dasar itu, QuantLab dikembangkan sebagai alat belajar mandiri yang menggabungkan dua pendekatan:

- **Analisa fundamental sederhana** untuk membaca kesehatan perusahaan melalui ROE, PBV, current ratio, dan perbandingan dengan median peer satu sektor yang berasal dari kupelajari diluar mata kuliah.
- **Analisa harga** untuk membaca return, beta, CAPM/Jensen, volatilitas, korelasi, dan risiko portofolio.

Proyek ini dikembangkan oleh **AUFOUNDATION** sebagai inisiatif belajar dan eksplorasi, bukan produk resmi kampus. Edisi ini fokus pada ticker **IDX** dan benchmark **IHSG**. Kode tersedia secara terbuka untuk dipelajari, dimodifikasi, dan difork untuk penggunaan non-komersial. Dilarang menjual atau memakai proyek ini untuk produk komersial tanpa izin tertulis AUFOUNDATION. Penambahan dataset ticker negara lain diperbolehkan untuk penggunaan non-komersial.

## Fitur

- Harga dari yfinance atau upload CSV investing.com.
- Return harian, mingguan, dan bulanan.
- Beta, CAPM, Jensen alpha, SD, CV, dan korelasi.
- Fundamental ROE, PBV, dan current ratio dari yfinance, CSV, atau editor manual.
- Median peer per sektor dan kuadran fundamental.
- Universe 976 emiten IDX dengan pencarian sektor, subsektor, dan kode.
- Asisten Qwen opsional dengan tiga mode: API lokal, copy-paste prompt, dan katalog offline.

## Persyaratan

- Python 3.10 atau lebih baru. Disarankan Python 3.12.
- Koneksi internet untuk yfinance.
- Qwen **tidak wajib**. Aplikasi tetap bisa dipakai tanpa model AI.

## Instalasi

```bash
git clone https://github.com/audrymirzaa/aufoundation-quantlab-id.git
cd aufoundation-quantlab-id

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Buka `http://localhost:8501`.

Alternatif di Windows: jalankan `Jalankan QuantLab.bat`.

## Menyambungkan Qwen

Qwen tidak dibundel di repo ini karena model berukuran besar dan dikelola sebagai server terpisah. QuantLab memanggil endpoint OpenAI-compatible memakai `requests`; tidak ada paket Python Qwen tambahan yang diperlukan.

### Ollama

```bash
ollama pull qwen2.5:3b
ollama serve
```

Di QuantLab:

1. Buka tab **Asisten AI**.
2. Buka **Pengaturan Qwen**.
3. Pilih **API lokal (OpenAI-compatible)**.
4. Isi endpoint `http://127.0.0.1:11434/v1`.
5. Isi model `qwen2.5:3b`.
6. Klik **Tes koneksi**.

Model lain bisa dipakai selama tersedia di Ollama, misalnya `qwen2.5:7b` bila RAM mencukupi.

### LM Studio

1. Muat model Qwen di LM Studio.
2. Jalankan local server pada port 1234.
3. Di QuantLab, isi endpoint `http://127.0.0.1:1234/v1`.
4. Isi nama model sesuai yang dimuat di LM Studio.
5. Klik **Tes koneksi**.

### API remote OpenAI-compatible

Isi endpoint, nama model, dan API key di **Pengaturan Qwen**. API key hanya disimpan di sesi Streamlit dan tidak ditulis ke repo. Jangan pernah commit API key.

### Tanpa Qwen

Pilih salah satu mode berikut:

- **Katalog offline**: mengambil ticker langsung dari `data/ticker_universe.csv`.
- **Copy-paste prompt**: QuantLab membuat prompt, lalu jawaban Qwen ditempel kembali ke aplikasi.

## Sumber data dan batasan

- Harga yfinance memakai harga adjusted.
- ROE memakai TTM return on equity, PBV memakai harga terakhir, dan CR memakai laporan terakhir.
- Bank umumnya tidak memiliki current ratio; nilai kosong tidak diisi nol.
- Maksimal 60 ticker diambil per percobaan.
- Qwen menerima maksimal 15 kandidat teratas agar respons lebih cepat; tabel tetap menampilkan semua kandidat dari universe.
- Universe emiten adalah snapshot, bukan daftar real-time. Detail sumber ada di [data/ticker_universe.source.txt](data/ticker_universe.source.txt).
- `data/fundamentals.csv` adalah data lokal pengguna dan tidak di-commit. Aplikasi tetap bisa membuat template dari tab Sektor & Kuadran.
- Data Yahoo/yfinance bisa terlambat, kosong, atau berbeda dari data IDX/RTI.

## Tes

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Build desktop opsional

Windows:

```bat
build_exe.bat
```

Hasil build ada di `dist/QuantLab.exe` dan `QuantLab.exe`. File binary tidak disimpan di repo; gunakan GitHub Releases bila ingin membagikannya.

## Struktur proyek

```text
app.py                  Aplikasi Streamlit
engine/                 Logika data, metrik, fundamental, universe, asisten
data/                   Universe, peta sektor, atribusi sumber
tests/                  Tes unit dan smoke test
scripts/                Skrip bantu
desktop_launcher.py     Launcher desktop opsional
```

## Lisensi

Kode QuantLab dilisensikan dengan **PolyForm Noncommercial 1.0.0**. Lihat [LICENSE](LICENSE). Lisensi ini mengizinkan penggunaan, perubahan, dan distribusi untuk tujuan non-komersial. Dilarang menjual atau menggunakan kode ini untuk produk komersial tanpa izin tertulis dari AUFOUNDATION.

Karena membatasi penggunaan komersial, proyek ini tidak dikategorikan sebagai open-source menurut definisi OSI. Istilah yang tepat adalah **source-available untuk penggunaan non-komersial**.

Data pihak ketiga memiliki ketentuan sendiri dan juga dibatasi untuk penggunaan non-komersial. Lihat [DATA_SOURCES.md](DATA_SOURCES.md) sebelum menggunakan atau mendistribusikan ulang data.

## Disclaimer

QuantLab adalah alat analisa dan edukasi, bukan nasihat investasi. Keputusan investasi sepenuhnya tanggung jawab pengguna.
