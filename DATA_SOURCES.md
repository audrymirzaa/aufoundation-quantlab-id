# Sumber Data dan Lisensi Pihak Ketiga

Lisensi **PolyForm Noncommercial 1.0.0** pada [LICENSE](LICENSE) berlaku untuk kode QuantLab dan membatasi penggunaan pada tujuan non-komersial. Data pihak ketiga tetap mengikuti ketentuan masing-masing.

## Universe emiten

- `data/ticker_universe.csv` adalah snapshot 976 emiten.
- Sumber utama: AITRADE.ID, https://aitrade.id/saham, snapshot 6 November 2026.
- Sumber board dan tanggal listing: wildangunawan/Dataset-Saham-IDX, https://github.com/wildangunawan/Dataset-Saham-IDX, berlisensi CC BY-NC 4.0.
- Lisensi CC BY-NC 4.0: https://creativecommons.org/licenses/by-nc/4.0/
- Sektor dan subsektor berasal dari AITRADE.ID. Sebagian sektor yang kosong diisi dari dataset GitHub atau inferensi.
- Detail atribusi ada di [data/ticker_universe.source.txt](data/ticker_universe.source.txt).

Lisensi CC BY-NC 4.0 membatasi penggunaan komersial. Sebelum memakai atau mendistribusikan ulang data ini untuk produk komersial, pastikan izin dari pemilik sumber. Ketentuan AITRADE.ID juga perlu diperiksa langsung.

## Harga dan fundamental

- Harga dan fundamental diambil dari Yahoo Finance melalui library yfinance.
- Penggunaan data Yahoo Finance tunduk pada ketentuan Yahoo Finance.
- Data dapat terlambat, tidak lengkap, atau berbeda dari data resmi IDX.
- Field fundamental yang dipakai: `returnOnEquity`, `priceToBook`, dan `currentRatio`, dengan fallback laporan keuangan dari yfinance.

## Qwen

- Qwen tidak dibundel di repo ini.
- Model dijalankan melalui Ollama, LM Studio, atau endpoint OpenAI-compatible lain.
- Lisensi model mengikuti distribusi model yang dipakai pengguna.

## Catatan

QuantLab tidak menjamin keakuratan data pihak ketiga. Jangan menganggap data ini sebagai nasihat investasi.
