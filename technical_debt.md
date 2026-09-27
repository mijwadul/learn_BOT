# 📋 Technical Debt & Architecture Backlog

Dokumen ini mencatat daftar *Technical Debt* (hutang teknis), potensi risiko arsitektur, dan rencana refaktorisasi pada sistem **BBMA Autonomous AI Trading Bot**.

---

## 📌 TD-001: Pemisahan Environment Secrets (`.env`) vs Runtime Trading Settings

* **Status:** `OPEN / PROPOSED`
* **Kategori:** Security, Architecture, System Reliability
* **Prioritas:** Medium (High Recommended sebelum Production Multi-Account)
* **Komponen Terdampak:**
  * [`backend/api/routers/risk_settings.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/api/routers/risk_settings.py)
  * [`backend/config.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/config.py)
  * [`backend/.env`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/.env)

---

### 1. Latar Belakang & Masalah (*Problem Statement*)
Saat ini, ketika pengguna mengubah parameter risiko atau ambang probabilitas AI melalui Dashboard UI (misalnya mengubah `AI_NORMAL_ENTRY_THRESHOLD`, `RISK_MODE`, `FIXED_LOT_SIZE`, `MAX_RISK_DOLLARS`, `MAX_RISK_PERCENT`, `MAX_LOT_CAP`), endpoint `POST /api/settings/risk` mengeksekusi fungsi:
```python
from dotenv import find_dotenv, set_key
dotenv_path = find_dotenv()
set_key(dotenv_path, "AI_NORMAL_ENTRY_THRESHOLD", str(Config.AI_NORMAL_ENTRY_THRESHOLD))
```
Kode ini memanipulasi teks file [`.env`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/.env) secara langsung pada saat runtime.

---

### 2. Analisis Risiko & Dampak (*Risks & Impacts*)

1. **Pelanggaran Prinsip *The Twelve-Factor App* (Konfigurasi vs Rahasia):**
   * File `.env` dirancang murni untuk menyimpan **Server Secrets & Static Credentials** (seperti `DB_PASSWORD`, `MT5_LOGIN`, `MT5_PASSWORD`, port, dan host).
   * Parameter trading adalah **Dynamic User Preferences / Runtime State**, bukan rahasia server. Mencampurkannya dalam satu file teks berpotensi membuka celah modifikasi pada variabel penting yang tidak seharusnya disentuh.

2. **Risiko Korupsi Format File (*File Corruption*):**
   * Penulisan teks langsung menggunakan `set_key` rentan terhadap *race condition*, masalah encoding, komentar yang hilang, atau kegagalan penulisan saat proses tak terduga (misal listrik padam atau crash proses).
   * Jika file `.env` rusak atau string terpotong, backend akan gagal start saat restart berikutnya karena gagal membaca `DB_PASSWORD` atau kredensial MT5.

3. **Keterbatasan Fleksibilitas Multi-Pair (*Lack of Granularity*):**
   * File `.env` bersifat *flat key-value*. Nilai seperti `AI_NORMAL_ENTRY_THRESHOLD=70.0` berlaku global untuk semua pair.
   * Padahal, setiap pair memiliki karakteristik volatilitas berbeda (misal: BTCUSD idealnya threshold 70%, sedangkan XAUUSD cukup 60%). Menyimpan konfigurasi di `.env` mempersulit penerapan *per-pair dynamic setting*.

4. **Ketiadaan Transaksi & Audit Log (No ACID Protection):**
   * Modifikasi file teks tidak memiliki rollback otomatis jika terjadi kegagalan sebagian (partial write).

---

### 3. Rencana Solusi Arsitektur (*Proposed Architecture*)

Menerapkan **Separation of Concerns** (Pemisahan Tanggung Jawab) antara kredensial statis dan pengaturan runtime:

```text
┌──────────────────────────────────────────────┐
│                  .env File                   │
│   (Read-Only saat Runtime, Akses Terbatas)   │
│   - DB_HOST, DB_PORT, DB_NAME, DB_PASSWORD   │
│   - MT5_SERVER, MT5_LOGIN, MT5_PASSWORD      │
└──────────────────────────────────────────────┘
                       ▲
                       │ Tidak boleh ditulis ulang oleh aplikasi
                       │
┌──────────────────────────────────────────────┐
│       backend/bot_settings.json              │
│       (atau Tabel DB: system_settings)       │
│   - risk_mode, fixed_lot_size, max_lot_cap   │
│   - ai_normal_entry_threshold (Global / Pair)│
│   - ai_runner_entry_threshold (Global / Pair)│
└──────────────────────────────────────────────┘
                       ▲
                       │ Dibaca & Ditulis oleh UI via API Router
```

#### Rencana Implementasi:
1. **Buat Modul `SettingsManager` (`backend/utils/settings_manager.py`):**
   * Menyediakan fungsi `get_setting(key, default)` dan `update_settings(dict_data)`.
   * Otomatis membuat file `bot_settings.json` dengan nilai default jika file belum ada.
   * Mendukung skema terstruktur (Global Settings + Per-Pair Overrides).
2. **Refaktorisasi [`risk_settings.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/api/routers/risk_settings.py):**
   * Hapus pemanggilan `set_key(dotenv_path, ...)` dan ketergantungan tulis pada file `.env`.
   * Ganti penyimpanan ke `SettingsManager`.
3. **Pembaruan [`config.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/config.py):**
   * Ambil nilai awal dari `SettingsManager`, dengan *fallback* ke default atau nilai `.env` lama untuk kompatibilitas ke belakang (*backward compatibility*).

---

### 4. Kriteria Keberhasilan (*Acceptance Criteria*)

- [ ] File [`.env`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/.env) tidak pernah disentuh/dimodifikasi lagi secara otomatis oleh skrip Python saat runtime.
- [ ] Pengguna tetap dapat mengubah Risk Mode, Lot Size, dan AI Threshold melalui Dashboard UI tanpa error.
- [ ] Pengaturan baru tersimpan persisten ke file `bot_settings.json` (atau database) dan tetap terbaca saat server direstart.
- [ ] Jika file `bot_settings.json` dihapus, sistem secara otomatis meregenerasi file baru dengan konfigurasi default yang aman.
- [ ] Jika file `.env` dikunci (*read-only permissions*), bot tetap dapat beroperasi dan menyimpan preferensi trading dengan normal.

---

## 📌 TD-002: Isolasi Data Multi-Pair pada Sampel Keputusan Live, Hard Negatives, & Retraining Pipeline

* **Status:** `RESOLVED / IMPLEMENTED`
* **Kategori:** Machine Learning, Data Integrity, Multi-Pair Architecture
* **Prioritas:** High / Critical (Wajib sebelum live trading aktif di >1 pair)
* **Komponen Terdampak:**
  * [`backend/database/models/trade.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/database/models/trade.py) (`LiveDecisionSample`, `TradeLog`, `TradeJournal`)
  * [`backend/database/models/rlhf.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/database/models/rlhf.py) (`HardNegative`, `ApprovedSetup`, `RejectedSetup`, `IgnoredSetup`)
  * [`backend/database/repositories/trade_repo.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/database/repositories/trade_repo.py) (`get_live_decision_samples_for_training`, `save_live_decision_sample`, `get_historical_pnl_feedback`)
  * [`backend/database/repositories/rlhf_repo.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/database/repositories/rlhf_repo.py) (`get_hard_negative_ids`, `get_approved_setup_ids`, `get_rejected_setup_ids`, `get_ignored_setup_ids`)
  * [`backend/agents/executor.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/executor.py) (`save_live_decision_sample`, loop `micro_retrain`)
  * [`backend/agents/data_miner.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/data_miner.py) (`load_live_decision_chunk`, `load_hard_negatives_and_rlhf`)
  * [`backend/agents/researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py) (`_fetch_rlhf_pnl_data`)

---

### 1. Latar Belakang & Masalah (*Problem Statement*)
Setelah penambahan fitur multi-pair (seperti penambahan pair USOIL di samping XAUUSD), tabel candlestick telah dipisahkan secara fisik (`market_data_xauusd`, `market_data_usoil`). Namun, seluruh pipeline feedback ML dan riwayat transaksi masih menggunakan skema sentral tanpa metadata `symbol`:
1. **`live_decision_samples`**: Tidak memiliki kolom `symbol`. Ketika trade XAUUSD mengalami kerugian (Loss) dan menjadi Hard Negative, feature vector XAUUSD (dengan skala harga ~$2,600, ATR dan volatilitas emas) ikut termuat saat fungsi `get_live_decision_samples_for_training()` dipanggil untuk pair USOIL (harga ~$70).
2. **`hard_negatives`**: Kolom `symbol` ada di ORM namun diabaikan pada fungsi `add_hard_negative()` dan `get_hard_negative_ids()`, sehingga semua error OOS/Live dianggap global.
3. **`trade_logs` & `trade_journal`**: Tidak memiliki kolom `symbol` eksplisit berindeks, menyebabkan feedback loop performa PnL pada AI Researcher mencampuradukkan riwayat trade antar-pair.

---

### 2. Analisis Risiko & Dampak (*Risks & Impacts*)

1. **Cross-Pair Feature Contamination (Data Poisoning):**
   * Pohon keputusan (*Decision Trees*) LightGBM untuk pair USOIL akan melakukan split percabangan fitur berdasarkan nilai-nilai ekstrem dari pair Emas.
2. **Negative Transfer & Pembobotan Salah Sasaran:**
   * Sampel Loss diberi bobot penalti agresif (`sample_weight = 3.5`). Model USOIL akan "dihukum" atas kondisi false-breakout yang terjadi di Emas, menyebabkan model kehilangan *edge* pada setup yang seharusnya valid.
3. **Korupsi Siklus Online Learning (Micro-Retrain):**
   * Siklus periodic micro-retrain per pair di `executor.py` memuat live feedback global dan menyuntikkannya ke model masing-masing pair tanpa filter.

---

### 3. Rencana Solusi Arsitektur (*Proposed Architecture*)

Menerapkan **Multi-Tenant Schema Partitioning berbasis Kolom `symbol` Berindeks**:

```text
┌────────────────────────────────────────────────────────┐
│             Database: live_decision_samples            │
│   (Kolom: id, ticket, setup_id, symbol [INDEX], ...)   │
└────────────────────────────────────────────────────────┘
          │                                  │
          ▼ (WHERE symbol = 'XAUUSD')         ▼ (WHERE symbol = 'USOIL')
┌───────────────────────────┐      ┌───────────────────────────┐
│ Micro-Retrain Model XAUUSD│      │  Micro-Retrain Model USOIL│
│ (models/XAUUSD/model.pkl) │      │  (models/USOIL/model.pkl) │
└───────────────────────────┘      └───────────────────────────┘
```

#### Rencana Implementasi:
1. **Database Schema & Migrations (`models/trade.py`, `models/rlhf.py`, `migrations.py`):**
   * Tambahkan kolom `symbol VARCHAR(20) DEFAULT 'XAUUSD' INDEX=True` pada `live_decision_samples`, `trade_logs`, `trade_journal`.
   * Pastikan kolom `symbol` pada `hard_negatives`, `approved_setups`, `rejected_setups`, `ignored_setups` memiliki indeks.
2. **Repository Layer (`trade_repo.py`, `rlhf_repo.py`):**
   * Tambahkan parameter wajib `symbol: str` pada fungsi `save_live_decision_sample()`, `get_live_decision_samples_for_training()`, `get_hard_negative_ids()`, dan `get_historical_pnl_feedback()`.
3. **Execution & Miner Layer (`executor.py`, `data_miner.py`, `researcher.py`):**
   * Teruskan `target_symbol` saat menyimpan sampel live dan riwayat transaksi.
   * Modifikasi siklus micro-retrain agar hanya memuat live feedback milik pair bersangkutan (`load_live_decision_chunk(mode, symbol=clean_p)`).
4. **Fresh Start Cleanup:**
   * Lakukan drop/truncate pada 7 tabel riwayat/sampel lama untuk memastikan dataset training bersih dari kontaminasi silang masa lalu.

---

### 4. Kriteria Keberhasilan (*Acceptance Criteria*)

- [x] Kolom `symbol` tersimpan dan terindeks di tabel `live_decision_samples`, `trade_logs`, dan `trade_journal`.
- [x] Fungsi `get_live_decision_samples_for_training(mode, symbol)` hanya mengembalikan sampel milik `symbol` yang diminta.
- [x] Siklus micro-retrain pada `executor.py` memproses feedback spesifik per pair tanpa data campuran.
- [x] Training OOS dan RLHF injection di `researcher.py` terisolasi per folder `models/{symbol}/`.
- [x] UI Journal dan Dashboard menampilkan badge pair yang presisi untuk setiap trade aktif dan riwayat deal.

---

### 5. Riwayat Perubahan (*Changelog*)
* **2026-09-26:** TD-001 dibuat (Pemisahan `.env` vs `bot_settings.json`).
* **2026-09-26:** TD-002 ditambahkan (Isolasi Data Multi-Pair pada Sampel Keputusan Live, Hard Negatives, & Retraining Pipeline).
* **2026-09-26:** TD-002 diselesaikan (`RESOLVED / IMPLEMENTED`) - Seluruh layer DB, Repositories, Agents, Routers, dan Frontend UI telah menerapkan isolasi partisi `symbol`.
* **2026-09-27:** TD-003 ditambahkan & diselesaikan (`RESOLVED / IMPLEMENTED`) - Perombakan Besar-Besaran Training Pipeline ke Binary Meta-Labeling, Institutional Two-Tier Targets, Alpha Feature Enrichment, & Purged Walk-Forward Time-Series Cross Validation.
* **2026-09-27:** TD-004 ditambahkan & diselesaikan (`RESOLVED / IMPLEMENTED`) - Modularisasi Dekomposisi Monolitik `researcher.py` (1.341 baris) menjadi Submodul Khusus di `research/` (`feature_engineer.py`, `optimizer.py`, `calibrator.py`, `model_manager.py`).
* **2026-09-27:** TD-005 ditambahkan & diselesaikan (`RESOLVED / IMPLEMENTED`) - Dekomposisi Monolitik Frontend Dashboard (`frontend/src/app/page.tsx` dari 1.249 baris ke ~370 baris) & Eliminasi Kalimat/Badge Redundan UI.

---

## 📌 TD-005: Dekomposisi Monolitik Frontend Dashboard (`page.tsx`) ke Subkomponen Terisolasi & Pembersihan Teks Redundan

* **Status:** `RESOLVED / IMPLEMENTED`
* **Kategori:** Frontend Architecture, UI/UX Cleanliness, Component Modularity
* **Prioritas:** Medium / High (Meningkatkan performa re-render dan keterbacaan kode UI)
* **Komponen Terdampak:**
  * [`frontend/src/app/page.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/app/page.tsx) (Menyusut dari 1.249 baris menjadi ~370 baris)
  * [`frontend/src/app/database/page.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/app/database/page.tsx) (Menghilangkan badge isolasi dan kalimat redundan yang di-screenshot user)
  * [`frontend/src/components/dashboard/DashboardHeader.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/DashboardHeader.tsx) (Baru: Multi-pair switcher, balance/equity/floating PnL/drawdown, master otak dropdown, live toggle)
  * [`frontend/src/components/dashboard/BrainTelemetryGrid.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/BrainTelemetryGrid.tsx) (Baru: 4 Kartu telemetri cerdas: AI Radar, Market Regime ADX, News Radar, Risk Guard)
  * [`frontend/src/components/dashboard/OpenPositionsTable.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/OpenPositionsTable.tsx) (Baru: Kartu mobile & tabel desktop posisi terbuka dengan aksi BE, 50% partial close, Close)
  * [`frontend/src/components/dashboard/LiveTerminalLogs.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/LiveTerminalLogs.tsx) (Baru: Streaming WebSocket terminal log viewer)
  * [`frontend/src/components/dashboard/MultiPairHealthGrid.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/MultiPairHealthGrid.tsx) (Baru: Grid status kesehatan & akurasi pair aktif)
  * [`frontend/src/components/dashboard/AddPairModal.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/AddPairModal.tsx) (Baru: Modal tambah pair dengan teks bersih bebas developer jargon)
  * [`frontend/src/components/dashboard/index.ts`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/dashboard/index.ts) (Baru: Barrel export)

### 1. Masalah yang Diselesaikan:
1. **Monolithic Page Component**: File `frontend/src/app/page.tsx` mencapai 1.249 baris berisi state management, streaming WebSocket log, render tabel open position, kartu telemetri probabilitas AI, dan modal dialog secara bercampur. Re-render sering terjadi ketika feed log streaming tiba.
2. **UI Clutter & Unnecessary Developer Fluff**: Pada halaman Database terdapat teks berulang yang tidak diperlukan:
   - Badge *"Tabel Database Terisolasi: market_data_btcusd"*
   - Paragraf *"Tarik data histori dan candle terkini khusus pair BTCUSD (BTCUSDm). Data disimpan ke tabel terisolasi tanpa mempengaruhi pair lainnya."*
3. **Penyusutan Kode Frontend**: Dashboard utama kini beroperasi sebagai *controller* ramping dengan pemisahan komponen UI yang modular dan mandiri.


---

## 📌 TD-003: Perombakan Arsitektur Pelatihan AI ke Binary Meta-Labeling, Institutional Two-Tier Targets, & Purged Walk-Forward CV

* **Status:** `RESOLVED / IMPLEMENTED`
* **Kategori:** Machine Learning, Quantitative Finance, Model Architecture
* **Prioritas:** Critical (Mendobrak batas Win Rate 50% & Meningkatkan Expectancy)
* **Komponen Terdampak:**
  * [`backend/agents/research/target_labeler.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/target_labeler.py)
  * [`backend/database/repositories/trade_repo.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/database/repositories/trade_repo.py)
  * [`backend/agents/researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py)
  * [`backend/agents/gatekeeper.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/gatekeeper.py)
  * [`backend/api/routers/rlhf.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/api/routers/rlhf.py)

### 1. Masalah yang Diselesaikan:
1. **Target Barrier Flaw**: Model sebelumnya terkunci di bawah win rate 50% karena menuntut target kaku 1:2 tanpa proteksi de-risking, dan menghukum trade profit pada horizon timeout sebagai loss (0).
2. **Multiclass Inefficiency**: Menggunakan klasifikasi 3-kelas (0, 1, 2) yang membuang kapasitas model untuk menebak arah yang sudah ditentukan oleh aturan teknikal BBMA.
3. **Data/Target Leakage**: Embargo hanya 30 bar saat target horizon melihat 120-300 bar ke depan.
4. **Regime Overfitting**: Hyperparameter Optuna hanya diuji pada 1 slice kronologis 75/25.

### 2. Solusi yang Diimplementasikan:
1. **Institutional Two-Tier Target Simulation**: TP1 pada 1.0R (lock profit & Breakeven trailing) + TP2 pada 2.0R (Normal) atau max_runner_rr (Runner) + Soft Timeout Barrier.
2. **Binary Meta-Labeling Formulation**: AI diformulasikan sebagai filter kualitas binary ($y \in \{0, 1\}$) memprediksi peluang menang $P(Win)$.
3. **Alpha Feature Enrichment**: Sesi perdagangan (London, NY, Asian, Overlap, Sin/Cos Hour & DOW), Bollinger Squeeze Percentile, ATR Burst Ratio, Rejection Wick Ratio, Relative Volume, dan Direction-Aligned Symmetric Setup Features.
4. **Purged Walk-Forward Time-Series CV**: 3-Fold Walk-Forward Cross Validation dengan purge window 150 bars pada Optuna objective.
5. **Gatekeeper & Live Inference Compatibility**: Mendukung output probabilitas binary meta-model secara langsung dan kompatibel ke belakang dengan model warisan.

---

## 📌 TD-004: Modularisasi Dekomposisi Monolitik `researcher.py` ke Submodul Spesialis di `research/`

* **Status:** `RESOLVED / IMPLEMENTED`
* **Kategori:** Code Cleanliness, Maintainability, Software Architecture
* **Prioritas:** High (Mengatasi Cognitive Overload & Duplikasi Logika Pelatihan)
* **Komponen Terdampak:**
  * [`backend/agents/researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py) (Menyusut dari 1.341 baris menjadi ~460 baris)
  * [`backend/agents/research/model_manager.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/model_manager.py) (Baru: Persistence, Paths, & Metadata JSON)
  * [`backend/agents/research/feature_engineer.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/feature_engineer.py) (Baru: Normalisasi ATR, Sesi, Fitur Arah Simetris, & Feature Locking)
  * [`backend/agents/research/optimizer.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/optimizer.py) (Baru: CPCV Purged Walk-Forward CV & Optuna Study)
  * [`backend/agents/research/calibrator.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/calibrator.py) (Baru: Dynamic Threshold Calibration & SQN Scoring)
  * [`backend/agents/research/__init__.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/__init__.py)

### 1. Masalah yang Diselesaikan:
1. **Monolithic Complexity**: File `researcher.py` membengkak hingga 1.341 baris dan 75 KB, mencampurkan urusan I/O disk, matematika fitur, Optuna CV, kalibrasi threshold, inferensi live, dan training chunk.
2. **Duplikasi Kode Masif**: Loop pelatihan chunk `train_normal_mode` dan `train_runner_mode` memiliki kesamaan 95% namun di-copy-paste dua kali (menghabiskan 400+ baris duplikat).
3. **Pemberian Bobot Arah yang Terisolasi**: Penentuan fitur arah (`setup_dir`) sebelumnya terpisah sehingga setup Buy dan Sell tidak dinormalisasi secara simetris sebelum ekstraksi fitur.

### 2. Solusi yang Diimplementasikan:
1. **Dekomposisi Submodul Terpisah**: Seluruh logika fitur, Optuna, kalibrasi, dan persistensi dipisahkan ke modul independen yang dapat diuji (*unit-testable*).
2. **Unified Training Pipeline (`_execute_training_pipeline`)**: Logika ekstraksi chunk, injeksi RLHF, live trade feedback, dan fitting model disatukan dalam satu pipeline bersih yang mendukung kedua mode secara mulus.
3. **100% Backward Compatibility**: Seluruh pemanggilan fungsi dan atribut publik (`add_normalized_features`, `features`, `optimal_threshold_normal`, `save_models`, dll.) tetap identik dan kompatibel penuh dengan `gatekeeper.py`, `executor.py`, dan router FastAPI.

