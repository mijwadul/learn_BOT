# 🗺️ Roadmap Arsitektur & Rencana Pengembangan
## BBMA Autonomous AI Trading Bot

> Dokumen ini adalah hasil analisis menyeluruh perbandingan antara blueprint 6-fase sistem trading AI dengan codebase aktual. Setiap fase diurutkan berdasarkan ketergantungan teknis — fase sebelumnya adalah prasyarat untuk fase berikutnya.
>
> **Terakhir diperbarui:** 2026-09-28

---

## 📊 Status Codebase Saat Ini (Ringkasan)

Codebase sudah **melampaui blueprint 6-fase** di hampir semua aspek. Arsitektur aktual jauh lebih canggih dari spesifikasi awal:

| Aspek | Blueprint Awal | Codebase Aktual |
|---|---|---|
| Model AI | Single model, 1 target | **Dual-model**: `model_normal` (1.5R) + `model_runner` (5.0R) |
| Target Labeling | Fixed ±pips TP/SL | **BBMA Lifecycle**: Adaptive ATR-based, 2-candle confirmation, CSM detection |
| Retraining | Offline cron | **2-tier**: Micro-retrain online + Full retrain via API |
| Data source | File/CSV statis | **Live MT5**: Streaming + eksekusi order real ke broker |
| Hyperparameter tuning | Optuna sederhana | **Purged Walk-Forward CV** (CPCV, 3-fold, purge 150 bar) |
| Multi-pair | Tidak ada | **5 pair terisolasi**: XAUUSD, BTCUSD, GBPUSD, USOIL, XNXX |
| Human feedback | Approve/Reject | **3 tier**: Approve (w=5.0) + Hard Negative (w=3.0) + Reject (w=0.1) |

### ✅ Pekerjaan yang Sudah Selesai (Historis)

- **TD-001 / Fase A** `RESOLVED` — Pemisahan Konfigurasi Runtime vs Environment Secrets (`bot_settings.json` + `SettingsManager`, `.env` read-only)
- **Fase B** `RESOLVED` — OOS Evaluator ("Fit & Proper Test" Gate via VectorBT)
- **Fase C** `RESOLVED` — Integrasi Vectorbt & Penyimpanan Scorecard Database (`model_scorecard` + API Endpoints)
- **TD-002** `RESOLVED` — Isolasi Data Multi-Pair (kolom `symbol` berindeks di semua tabel)
- **TD-003** `RESOLVED` — Perombakan ke Binary Meta-Labeling + Institutional Two-Tier Targets + Purged Walk-Forward CV
- **TD-004** `RESOLVED` — Modularisasi `researcher.py` (1.341 baris) ke submodul `research/`
- **TD-005** `RESOLVED` — Dekomposisi Frontend Dashboard monolitik ke subkomponen terisolasi
- **CLEANUP** `DONE` — Hapus dependency zombie `xgboost` dari `Requirements.txt` (tidak pernah digunakan di codebase)

---

## 🔗 Peta Ketergantungan Antar Fase

```
[Fase B: OOS Evaluator — Fit & Proper Test]  ←── Prasyarat untuk Fase C & D
         │
         ├──────────────────────┐
         ▼                      ▼
[Fase C: VBT Integration]  [Fase D: Scheduling Otomatis]
         │                      │
         └──────────┬───────────┘
                    ▼
         [Fase E: Model Scorecard di Frontend]
```

---

## 📌 Fase B: OOS Evaluator — "Fit & Proper Test" Gate

**Status:** `RESOLVED` | **Prioritas:** High | **Prasyarat:** Tidak ada (independen)

### Latar Belakang

Ini adalah **gap terbesar** yang ditemukan dari analisis arsitektur. Saat ini pipeline pelatihan berjalan sebagai berikut:

```
Optuna (temukan best_params) → Train model → Calibrate threshold → Save model → Deploy ke live
```

Tidak ada tahap verifikasi finansial sebelum model di-deploy. Model langsung aktif ke live trading tanpa pernah "diuji" dalam simulasi yang akurat secara finansial.

### Konsep: Fit & Proper Test Gate

Vectorbt digunakan sebagai **gerbang kualitas offline** — bukan sebagai komponen live trading. Model hanya boleh masuk ke pasar nyata jika lolos simulasi finansial di data yang belum pernah dilihatnya (OOS):

```
Optuna → Train → Calibrate → [VBT OOS Simulation] → PASS? → Save & Deploy
                                                    → FAIL? → Pertahankan model lama
```

### Mengapa Tidak Perlu Perubahan Database

ATR, SL, dan TP **tidak perlu disimpan di database**. Mereka dihitung on-the-fly dari OHLCV yang sudah ada, menggunakan fungsi yang sudah eksis (`generate_targets()`):

```python
# Alur di memory — tidak ada fetch DB tambahan:
df_oos = fetch_oos_from_db()          # ← OHLCV biasa dari tabel yang sudah ada
df_oos = researcher.generate_targets(df_oos)  # ← ATR_14, LWMA, EMA dihitung di sini
df_oos = researcher.add_normalized_features(df_oos)

# Pre-compute SL/TP per candle dari kolom yang sudah ada:
atr    = df_oos['ATR_14'].values
close  = df_oos['close'].values
sl_pct = (1.2 * atr) / close         # SL relatif terhadap harga
tp_pct = (rr_ratio * 1.2 * atr) / close

# Pass ke vectorbt:
portfolio = vbt.Portfolio.from_signals(
    close=close, entries=buy_signals, short_entries=sell_signals,
    sl_stop=sl_pct, tp_stop=tp_pct, fees=spread_fee
)
```

### Modul Baru yang Perlu Dibuat

**`backend/agents/research/oos_evaluator.py`**

```python
def run_fit_proper_test(model, researcher, df_oos, mode, symbol) -> dict:
    """
    Jalankan simulasi VBT pada data OOS.
    Return: scorecard + keputusan pass/fail.
    """
    # 1. Generate features & signals
    # 2. Filter by probability threshold
    # 3. Pre-compute dynamic SL/TP dari ATR
    # 4. Run vbt.Portfolio.from_signals()
    # 5. Extract stats: Sharpe, Drawdown, PF, Win Rate, Trades
    # 6. Evaluate against minimum thresholds
    # 7. Return scorecard dict
```

### Threshold Kelulusan Minimum

| Metrik | Normal Mode (RR 1:1.5) | Runner Mode (RR 1:5) |
|---|---|---|
| Win Rate | ≥ 52% | ≥ 28% |
| Profit Factor | ≥ 1.3 | ≥ 1.2 |
| Sharpe Ratio | ≥ 0.8 | ≥ 0.5 |
| Max Drawdown | ≤ 20% | ≤ 35% |
| Min Trades (signifikansi statistik) | ≥ 30 | ≥ 20 |

### Perubahan di Pipeline Training

Di [`researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py) setelah baris `calibrate_optimal_threshold()`:

```python
# Sebelum (langsung save):
cal_th = self.calibrate_optimal_threshold(...)
self.save_models()

# Sesudah (ada gate):
cal_th = self.calibrate_optimal_threshold(...)
oos_report = run_fit_proper_test(model, self, df_oos, mode_str, target_sym)
if oos_report["passed"]:
    self.oos_scorecard = oos_report
    self.save_models()  # Hanya save jika lolos
else:
    logger.warning(f"⚠️ Model GAGAL Fit & Proper Test. Model lama dipertahankan.")
    # Simpan laporan gagal untuk analisis
```

### Dependency Baru

```
Requirements.txt:
+ vectorbt
```

> **Catatan**: `numba` (dependency vectorbt) mempunyai JIT cold-start 30-60 detik pertama kali dijalankan. Ini tidak masalah karena VBT hanya dijalankan sekali setelah training selesai (bukan di loop live).

### Kriteria Selesai

- [x] `oos_evaluator.py` terbuat di `backend/agents/research/`
- [x] Pipeline training memanggil evaluator setelah calibrate_threshold
- [x] Model tidak tersimpan jika gagal Fit & Proper Test
- [x] Scorecard tersimpan ke `models_metadata.json` (extend struktur yang ada)
- [x] API endpoint untuk trigger evaluasi manual: `POST /api/strategies/evaluate-oos`

---

## 📌 Fase C: Integrasi Vectorbt & Penyimpanan Scorecard

**Status:** `RESOLVED` | **Prioritas:** Medium | **Prasyarat:** Fase B harus selesai

### Latar Belakang

Setelah `oos_evaluator.py` (Fase B) berhasil menghasilkan data, fase ini bertujuan:
1. Menyimpan scorecard ke database secara persisten (bukan hanya JSON)
2. Menyediakan endpoint API yang kaya untuk mengambil riwayat scorecard
3. Memungkinkan perbandingan scorecard antar versi model

### Skema Database Baru

Tabel baru: `model_scorecard`

```sql
CREATE TABLE model_scorecard (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    mode        VARCHAR(10) NOT NULL,  -- 'normal' / 'runner'
    trained_at  TIMESTAMP NOT NULL,
    -- Metrik finansial dari VBT
    total_trades    INTEGER,
    win_rate        FLOAT,
    profit_factor   FLOAT,
    sharpe_ratio    FLOAT,
    max_drawdown    FLOAT,
    total_return    FLOAT,
    -- Status kelulusan
    passed          BOOLEAN NOT NULL,
    failure_reason  TEXT,
    -- Metadata
    threshold_used  FLOAT,
    oos_start_date  TIMESTAMP,
    oos_end_date    TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);
```

### Endpoint API Baru

```
GET  /api/strategies/scorecard?symbol=XAUUSD&mode=normal
     → Riwayat scorecard model (tabel kronologis)

GET  /api/strategies/scorecard/latest?symbol=XAUUSD
     → Scorecard terkini untuk kedua mode

POST /api/strategies/evaluate-oos
     → Trigger evaluasi manual OOS (tanpa retrain)
```

### Kriteria Selesai

- [x] Tabel `model_scorecard` tersedia di database
- [x] Setiap training yang berhasil/gagal mencatat entri ke tabel ini
- [x] Endpoint `GET /api/strategies/scorecard` mengembalikan riwayat yang dapat di-page
- [x] Data tersedia untuk dikonsumsi oleh frontend (Fase E)

---

## 📌 Fase D: Scheduling Otomatis Retraining

**Status:** `OPEN` | **Prioritas:** Low–Medium | **Prasyarat:** Fase B harus selesai

### Latar Belakang

Saat ini retraining hanya bisa dipicu manual via API atau tombol di UI. Tidak ada mekanisme otomatis yang memastikan model selalu segar. Blueprint awal menyebut Apache Airflow atau cron — kita perlu ekuivalen yang lebih ringan.

### Pendekatan yang Direkomendasikan

Karena backend sudah menggunakan `asyncio` dan FastAPI, pendekatan paling ringan adalah **`APScheduler`** (tidak perlu Airflow/Celery):

```python
# backend/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Micro-retrain: setiap 6 jam (sudah ada di executor, tinggal di-schedule)
scheduler.add_job(trigger_micro_retrain_all_pairs, 'interval', hours=6)

# Full retrain + Fit & Proper Test: setiap Minggu (setelah market tutup)
scheduler.add_job(trigger_full_retrain_pipeline, 'cron',
                  day_of_week='sun', hour=2)  # Minggu 02:00 WIB
```

### Trigger Kondisional

Full retrain otomatis juga dipicu jika kondisi ini terpenuhi:
- Win Rate live dalam 7 hari terakhir turun > 5% dari baseline scorecard
- Lebih dari 50 feedback baru (Approve/Reject) masuk sejak training terakhir

### Kriteria Selesai

- [ ] `APScheduler` terinstall dan berjalan saat startup FastAPI
- [ ] Jadwal micro-retrain 6 jam aktif untuk semua pair
- [ ] Jadwal full retrain mingguan aktif dengan Fit & Proper Test gate (Fase B)
- [ ] Log scheduler tersedia di terminal dan halaman Logs frontend
- [ ] Trigger kondisional berdasarkan degradasi performa live

---

## 📌 Fase E: Model Scorecard Dashboard di Frontend

**Status:** `RESOLVED` | **Prioritas:** Low | **Prasyarat:** Fase B + Fase C harus selesai

### Latar Belakang

Saat ini frontend tidak memiliki cara untuk melihat "kesehatan" model AI. Pengguna tidak tahu apakah model yang aktif sudah lulus Fit & Proper Test, kapan terakhir dilatih, atau seberapa baik performanya di OOS.

### Konten Halaman Baru: `/strategies` (Extend)

Halaman strategies yang sudah ada diperkaya dengan seksi **"Model Health Report"**:

#### Kartu Status Per Pair

```
┌─────────────────────────────────────────────────┐
│  XAUUSD  |  Normal Mode  |  ✅ LULUS (2026-09-27)│
├─────────────────────────────────────────────────┤
│  Win Rate: 58.3%    │  Profit Factor: 1.82      │
│  Sharpe:   1.24     │  Max Drawdown: 11.2%      │
│  Total Trades: 143  │  OOS Period: Jul–Sep 2026  │
├─────────────────────────────────────────────────┤
│  Threshold Aktif: 62.0%  │  OOS Return: +18.7%  │
└─────────────────────────────────────────────────┘
```

#### Equity Curve

Visualisasi kurva ekuitas model di data OOS menggunakan `lightweight-charts` (library yang sudah terinstall).

### Kriteria Selesai

- [x] Kartu "Model Health Report" tampil di halaman Strategies untuk setiap pair
- [x] Badge ✅ LULUS / ❌ GAGAL / 🔄 BELUM DIEVALUASI
- [x] Equity curve dari data VBT OOS ditampilkan
- [x] Riwayat scorecard (tabel kronologis versi model) tersedia

---

## 📋 Changelog

| Tanggal | Event |
|---|---|
| 2026-09-26 | TD-001 dibuat (Pemisahan `.env` vs runtime settings) |
| 2026-09-26 | TD-002 selesai (Isolasi Multi-Pair dengan kolom `symbol` berindeks) |
| 2026-09-27 | TD-003 selesai (Binary Meta-Labeling + Institutional Two-Tier Targets + Purged Walk-Forward CV) |
| 2026-09-27 | TD-004 selesai (Modularisasi `researcher.py` ke submodul `research/`) |
| 2026-09-27 | TD-005 selesai (Dekomposisi Frontend Dashboard monolitik ke subkomponen) |
| 2026-09-28 | Analisis gap blueprint 6-fase vs codebase aktual dilakukan |
| 2026-09-28 | `xgboost` dihapus dari `Requirements.txt` (zombie dependency — tidak digunakan di kode manapun) |
| 2026-09-28 | Roadmap Fase A–E dirumuskan berdasarkan analisis gap dan diskusi arsitektur |
| 2026-09-28 | Fase A selesai: SettingsManager diimplementasikan, runtime settings dipisah ke bot_settings.json, .env sepenuhnya read-only |
| 2026-09-28 | Fase B selesai: VectorBT OOS Evaluator, Fit & Proper Test Gate, dan endpoint /api/strategies/evaluate-oos diimplementasikan |
| 2026-09-28 | Fase C selesai: Tabel model_scorecard, repository, dan API endpoint scorecard/scorecard latest diimplementasikan |
| 2026-09-28 | Fase E selesai: Model Health Report, Equity Curve (lightweight-charts), Scorecard History, dan trigger on-demand OOS di frontend selesai |

