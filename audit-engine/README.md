# 🛡️ Autonomous Web3 Smart Contract Audit Engine (24/7)

Sistem audit keamanan *smart contract* otonom yang bekerja di latar belakang memonitor, meng-clone, menganalisis, dan menyusun laporan kerentanan berstandar **Cantina**, **Immunefi**, **Code4rena**, dan **Sherlock**.

---

## 🚀 Fitur Utama

1. **Autonomous 24/7 Target Fetcher:**
   - Memonitor rilis repositori kontes baru dari Code4rena dan Sherlock.
   - Otomatis melakukan `git clone` dan inisialisasi dependensi (`forge install` / `npm install`).
2. **Dual Engine Static Security Scanning:**
   - **Aderyn** (Rust AST static analyzer by Cyfrin).
   - **Slither** (Static analysis framework by Trail of Bits).
3. **Semantic Invariant & Logic Auditor:**
   - Mengekstrak kontrak inti, menganalisis pola *flash loan*, manipulasi oracle, *reentrancy*, *access control*, dan *precision loss*.
4. **Foundry PoC Validator:**
   - Menyusun skrip pengujian `.t.sol` untuk membuktikan celah keamanan di lingkungan lokal Foundry.
5. **Submission-Ready Report Generator:**
   - Menghasilkan laporan Markdown siap *submit* ke Cantina, Immunefi, atau Code4rena.
   - Mendukung notifikasi instan via Telegram / Discord.

---

## 📂 Struktur Direktori

```text
audit-engine/
├── config.py                 # Konfigurasi path, threshold, & webhook notifikasi
├── main.py                   # CLI Orchestrator & Daemon Runner
├── run.sh                    # Shell runner otomatis (export PATH & venv)
├── fetcher/
│   └── contest_fetcher.py   # Scraper kontes GitHub (Code4rena / Sherlock)
├── analyzers/
│   └── static_engine.py     # Integrasi Aderyn & Slither
├── llm_core/
│   └── semantic_auditor.py  # Ekstraktor konteks & analisa invariant
├── poc_generator/
│   └── forge_validator.py   # Foundry PoC executor (.t.sol)
├── reporter/
│   └── report_builder.py    # Generator laporan Markdown & Webhook alert
└── storage/
    ├── repos/               # Clone target repositori
    ├── reports/             # Laporan hasil audit (.md)
    └── cache/               # Riwayat repo yang sudah pernah di-scan
```

---

## ⚡ Cara Menjalankan

### 1. Periksa Kesiapan Toolchain
```bash
./run.sh --check-tools
```

### 2. Jalankan Mode 24/7 Background Daemon (Saat Anda Nonton / Idle)
```bash
./run.sh --daemon
```
Engine akan memeriksa repositori kontes baru secara berkala, melakukan audit mendalam, dan menyimpan laporannya secara otomatis.

### 3. Scan Folder / Repositori Lokal Tertentu
```bash
./run.sh --scan-local /path/ke/repo/kontrak
```

### 4. Lihat Daftar Laporan Temuan yang Tersedia
```bash
./run.sh --list-reports
```

---

## 🔔 Mengaktifkan Notifikasi HP (Opsional)
Untuk menerima notifikasi instan di Telegram saat sistem menemukan celah *High/Medium*, atur environment variable di `config.py` atau export:
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
```
