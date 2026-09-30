# 📋 Arsitektur Kuantitatif & Dokumentasi Eradikasi Technical Debt (Institutional Overhaul)

Dokumen ini memuat catatan komprehensif penghapusan seluruh hutang teknis (*technical debt*) lama dan pembaruan arsitektur model AI (LightGBM), metodologi pelabelan kuantitatif, isolasi data Out-Of-Sample (OOS), serta sekring eksekusi live berstandar *Quant Hedge Fund*.

---

### 1. 🛡️ ERADIKASI RACUN: Eliminasi Hard Negative Poison Loop & Ground-Truth Distortion
* **Status:** `RESOLVED` ✅ | **Prioritas:** `KRITIS (P0)` | **Komponen:** [`researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py), [`oos_evaluator.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/oos_evaluator.py), [`data_miner.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/data_miner.py)
* **Latar Belakang Masalah:**  
  Setiap kali model selesai dievaluasi, seluruh trade yang merugi pada backtest OOS (100–1.200 sampel) dipanen secara otomatis ke tabel database `hard_negatives`. Saat pelatihan berikutnya, sampel-sampel ini diinjeksi ke dataset training dan label aslinya diubah paksa:
  ```python
  # KODE LAMA BERBAHAYA:
  y_target.iloc[i] = 0       # Merusak ground truth
  sample_weights[i] = 2.5    # Penalti ekstrem
  ```
  Pasar finansial bersifat stokastik; setup teknikal BBMA yang valid pun wajar mengalami stop out akibat fluktuasi acak dan spread. Mengubah label menjadi `0` secara paksa merusak distribusi data dan membuat pohon LightGBM mengalami *Catastrophic Inhibition* (lumpuh / takut entry), sehingga Win Rate anjlok dari 35% ke 22% dan Sharpe merosot ke -1.68 di setiap iterasi incremental.
* **Solusi Terimplementasi:**  
  1. **Ground-Truth Preservation:** Menghapus manipulasi `y_target = 0`. Label murni ditentukan oleh pergerakan harga (*price action* dan *Triple Barrier*).
  2. **Hentikan Auto-Harvest OOS Losses:** Menghapus pemanenan trade rugi backtest OOS ke tabel database.
  3. **Isolasi Training Chunks:** Menghentikan injeksi data OOS ke dalam chunk pelatihan di `data_miner.py`.
  4. **Human RLHF Only:** Feedback trader manual (Approved/Rejected) hanya memengaruhi bobot sampel secara proporsional (`1.5x` / `0.6x`), tanpa mengubah label biner.

---

### 2. 🎯 HARMONISASI TARGET: Sinkronisasi Target Labeler vs Simulasi VectorBT OOS
* **Status:** `RESOLVED` ✅ | **Prioritas:** `KRITIS (P0)` | **Komponen:** [`target_labeler.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/target_labeler.py), [`oos_evaluator.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/oos_evaluator.py), [`optimizer.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/optimizer.py), [`calibrator.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/calibrator.py)
* **Latar Belakang Masalah:**  
  Terjadi ketidaksinkronan parah antara objektif saat training dan saat evaluasi kelulusan OOS:
  - Di `target_labeler.py`: Model diberi label `Target_Runner = 1` jika Maximum Favorable Excursion (MFE) mencapai $\ge 3.0\text{R}$ dengan trailing breakeven di $1.0\text{R}$.
  - Di `oos_evaluator.py` (VectorBT): TP Runner dihitung berbasis `rr_ratio * frac_cap * 1.2 * ATR` di mana `rr_ratio = 5.0` dan `frac_cap` (1.0 s.d. 3.0), menghasilkan target TP sebesar **$5.0\text{R} - 15.0\text{R}$** tanpa trailing stop!
  - Posisi yang mencapai $+3.8\text{R}$ (sukses di training) berbalik turun dan kena stop loss di VectorBT, dicatat sebagai kegagalan OOS, dan memicu penalti.
* **Solusi Terimplementasi:**  
  1. Menyelaraskan rasio TP Runner pada VectorBT menjadi presisi **$3.0\text{R}$** (`(3.0 * 1.2 * ATR) / close`), identik dengan kriteria `Target_Runner` di labeler.
  2. Menyelaraskan rentang optimasi Optuna dan pencarian threshold Runner ke probabilitas empiris ($0.38 - 0.65$) dengan benchmark target Win Rate institusional $28\%$.

---

### 3. 🔬 ERADIKASI DATA SNOOPING: Isolasi Blind Holdout OOS & Validation Slice
* **Status:** `RESOLVED` ✅ | **Prioritas:** `TINGGI (P1)` | **Komponen:** [`researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py)
* **Latar Belakang Masalah:**  
  Sebelumnya, kalibrasi threshold optimal (`calibrate_optimal_threshold`) dijalankan langsung pada dataset `_df_oos_for_calib` (data OOS holdout). Setelah itu, `run_fit_proper_test` menguji model pada data OOS yang sama. Ini merupakan pelanggaran kaidah *Holdout Contamination* dalam kuantitatif finansial (data yang dipakai kalibrasi tidak lagi bersifat *Out-Of-Sample*).
* **Solusi Terimplementasi:**  
  1. Threshold optimal dikalibrasi secara eksklusif pada **Validation Slice** kronologis (20% akhir dari data training `X_full`).
  2. Dataset OOS (20% akhir riwayat pasar) dipertahankan **100% blind** sebagai gerbang pengujian kelayakan independen yang steril dari proses kalibrasi parameter.

---

### 4. 🚀 PERBAIKAN RUNNER KILLER: Dynamic Exhaustion Exit pada Eksekutor Live
* **Status:** `RESOLVED` ✅ | **Prioritas:** `KRITIS (P0)` | **Komponen:** [`executor.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/executor.py), [`researcher.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/researcher.py)
* **Latar Belakang Masalah:**  
  Di `researcher.py`, `get_live_probabilities()` me-reset probabilitas `p_buy_r = 0.0` jika candle terakhir tidak sedang berada di dalam zona Re-entry LWMA (`setup_dir != 1`). Akibatnya, begitu sebuah posisi runner buy masuk pasar dan harga bergerak naik menjauhi zona entry menuju profit, pengecekan exhaust setiap 5 detik di `executor.py` mendeteksi `p_buy_r == 0.0 < 0.35` dan langsung **menutup paksa order**. Runner tidak pernah bisa berjalan lebih dari beberapa bar.
* **Solusi Terimplementasi:**  
  1. Mengembalikan unmasked raw probabilities (`runner_raw`, `normal_raw`) di `get_live_probabilities()`.
  2. Mengubah aturan Dynamic Exhaustion Exit: Posisi Runner tidak ditutup hanya karena keluar dari zona entry. Likuidasi dini HANYA terjadi jika:
     - Muncul sinyal pembalikan arah lawan yang sangat kuat ($P \ge 65\%$), ATAU
     - Terjadi pelanggaran struktur kaedah BBMA (Close menembus Lower BB untuk Buy, atau Close menembus Upper BB untuk Sell).

---

### 5. 📦 PENANGGULANGAN METADATA BLOAT: Sanitasi File `models_metadata.json`
* **Status:** `RESOLVED` ✅ | **Prioritas:** `SEDANG (P2)` | **Komponen:** [`model_manager.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/agents/research/model_manager.py)
* **Latar Belakang Masalah:**  
  File `models_metadata.json` membengkak hingga **15.152 baris (400 KB)** karena menyimpan seluruh riwayat array `losing_records` (ribuan objek trade) ke dalam file konfigurasi JSON. Ini membebani disk I/O, memperlambat parsing frontend, dan memperbesar risiko kegagalan read/write.
* **Solusi Terimplementasi:**  
  1. Menambahkan metode sanitasi `ModelManager._clean_scorecard()` yang membuang data trade individual yang berat sebelum serialisasi.
  2. File `models_metadata.json` disederhanakan dari 15.000+ baris menjadi $< 60$ baris yang hanya memuat metrik ringkasan portofolio dan kurva ekuitas terkompresi.

---

### 6. 👑 KEDAULATAN TRADER & EVALUASI FLEKSIBEL (Trader Sovereignty in Model Promotion)
* **Status:** `RESOLVED` ✅ | **Prioritas:** `TINGGI (P1)` | **Komponen:** [`ConfirmSaveModelModal.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/strategies/ConfirmSaveModelModal.tsx), [`strategies.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/api/routers/strategies.py)
* **Latar Belakang & Filosofi:**  
  Meskipun uji kelayakan OOS (Fit & Proper Test) menetapkan batas kelulusan institusional ketat, dalam riset quant terapan model yang belum lolos 100% kriteria seringkali menunjukkan peningkatan (*improvement*) berharga pada metrik tertentu (misalnya Sharpe Ratio meningkat, Profit Factor naik, atau Drawdown mengecil). Oleh karena itu, hak prerogatif untuk **Simpan & Timpa** atau **Tolak & Buang** model hasil pelatihan sepenuhnya dikembalikan ke tangan trader.
* **Solusi Terimplementasi:**  
  1. **Akses Penuh Tanpa Hambatan:** Tombol "Simpan & Timpa Model (.pkl)" dan "Tolak & Buang Model Ini" dapat dipilih langsung oleh trader secara transparan sesuai penilaian performa metrik yang ditampilkan.
  2. **Bebas Risiko Database Poisoning:** Berkat penghapusan Hard Negative Poison Loop (Poin #1), menyimpan model yang belum lolos OOS kini **100% aman dan tidak akan lagi meracuni database pelatihan** ataupun merusak ground-truth pada pelatihan berikutnya.
  3. **Quarantine Governance:** Supervisor secara cerdas menandai model yang belum lolos OOS ke status karantina jika belum mencapai ambang batas, namun tetap mengizinkan trader menggunakannya secara fleksibel.

---

### 7. 🧬 MODULARITAS UI & BATCH TRAINING QUEUE PIPELINE (Institutional Workflow)
* **Status:** `RESOLVED` ✅ | **Prioritas:** `FITUR & ARSITEKTUR` | **Komponen:** [`strategies/page.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/app/strategies/page.tsx), [`incubator/page.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/app/incubator/page.tsx), [`TrainingQueueCard.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/strategies/TrainingQueueCard.tsx), [`QueueConfirmModal.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/strategies/QueueConfirmModal.tsx), [`strategies.py`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/api/routers/strategies.py), [`Sidebar.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/Sidebar.tsx)
* **Latar Belakang & Filosofi:**  
  Halaman *Strategies* sebelumnya mencampurkan konfigurasi risiko transaksi dengan instrumen riset dan pelatihan AI yang berat. Hal ini membingungkan operasional harian trading dengan aktivitas eksperimen kuantitatif. Selain itu, pelatihan multi-mode atau multi-pair harus dijalankan satu per satu secara manual.
* **Solusi Terimplementasi:**  
  1. **Pemisahan Antarmuka (UI Separation):**
     - Halaman [`/strategies`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/app/strategies/page.tsx) kini murni dikhususkan untuk **Risk Management** (Dynamic Lot Sizing) dan **AI Signal Entry Threshold** (Inference Threshold).
     - Dibuat halaman mandiri [`/incubator`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/app/incubator/page.tsx) (**AI Incubator & Training Lab**) yang mengonsolidasikan Pair Selector, Reset Otak, Batch Queue Training, Model Status Grid, Feature Importance, Model Scorecard (OOS Test), RLHF Review, dan dialog evaluasi model.
     - Ditambahkan menu navigasi baru "AI Incubator" di [`Sidebar.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/Sidebar.tsx) dengan ikon `Brain`.
  2. **Batch Training Queue Pipeline:**
     - Dibuat [`TrainingQueueManager`](file:///d:/Titip/Dulinan/Trading%20BOT/backend/api/routers/strategies.py) di backend untuk mengeksekusi serangkaian tugas latihan secara sekuensial (FIFO) pada background worker thread.
     - Dibuat antarmuka penyusun antrean [`TrainingQueueCard.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/strategies/TrainingQueueCard.tsx) lengkap dengan preset cepat (`+ Both Full`, `+ Both Incremental`, `+ All Pairs`).
  3. **Modal Konfirmasi Antrean & Pilihan Pasca Pelatihan:**
     - Sebelum antrean dieksekusi, modal konfirmasi [`QueueConfirmModal.tsx`](file:///d:/Titip/Dulinan/Trading%20BOT/frontend/src/components/strategies/QueueConfirmModal.tsx) menampilkan ringkasan tugas dan meminta trader menentukan status akhir sistem:
       - **Kembali ke IDLE (Standby):** Sistem standby dan tidak membuka posisi otomatis, memberi ruang bagi trader untuk mereview metrik model baru.
       - **Beralih ke FORCE LIVE:** Sistem secara otomatis langsung mengaktifkan LIVE trading sesaat setelah seluruh rangkaian antrean tugas selesai dijalankan.

