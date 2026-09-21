# 🛠️ Technical Debt & Rencana Arsitektur (Roadmap)

Dokumen ini mencatat *Technical Debt* (hutang teknis) yang ada pada arsitektur bot saat ini, khususnya mengenai kekakuan algoritma dalam merespons dinamika pasar yang volatil. Solusi yang dirumuskan di bawah ini akan diimplementasikan pada pembaruan mendatang agar bot dapat beradaptasi (belajar) secara otomatis dari kegagalannya.

## 1. Algoritma Pembelajaran Statis (Hardcoded Hyperparameters)

**Status Saat Ini (Debt):**
Saat ini, ketika bot menyentuh batas *Drawdown* maksimal (*Circuit Breaker*) dan masuk ke fase Karantina/Riset, sistem akan melatih ulang model LightGBM dengan data terbaru. Namun, **parameter struktural AI (Hyperparameters)** seperti `learning_rate`, `max_depth`, dan `num_leaves` di dalam `researcher.py` bernilai absolut statis (*hardcoded*). Hal ini terbukti menjadi masalah: karena jika algoritma dengan racikan parameter tersebut terbukti gagal menghasilkan profit di market yang volatil, mengulang pelatihan dengan parameter yang persis sama kemungkinan besar akan menghasilkan kegagalan yang sama.

**Rencana Solusi (Auto-Hyperparameter Tuning via Optuna):**
*   Mengintegrasikan *library* **Optuna** ke dalam fase riset (`train_models`).
*   Saat retraining dilakukan, AI akan secara mandiri menjalankan ratusan iterasi simulasi untuk mencari konfigurasi parameter algoritma (Hyperparameter) terbaik yang paling tahan banting terhadap kondisi data market terbaru.
*   **Aturan Ketat:** Hanya parameter AI (LightGBM) yang boleh beradaptasi. Parameter indikator teknikal (seperti periode Bollinger Bands, EMA, dan standar deviasi) akan **dibiarkan tetap statis (hardcoded)** sesuai dengan paten strategi fundamental.

## 2. Ketiadaan Umpan Balik Finansial (No PnL Feedback Loop)

**Status Saat Ini (Debt):**
Sistem saat ini mengandalkan *Incremental Learning* yang menilai target profit/loss secara teoritis berdasarkan data *candlestick* semata. Sistem belum memiliki "memori rasa sakit" terkait transaksi riil yang merugikan. Akibatnya, setup yang secara riwayat eksekusi *live* terbukti selalu mengalami *loss* secara finansial tidak secara langsung dihukum dalam proses pelatihan model.

**Rencana Solusi (Reinforcement Loop & Penalti Bobot):**
*   Membangun jembatan (*pipeline*) data antara agen eksekutor (`executor.py`) dengan agen periset (`researcher.py`) melalui database.
*   Jika bot mengeksekusi suatu posisi dan berujung pada kerugian finansial di akun *live*, ID dan karakteristik setup tersebut akan dicatat ke dalam tabel khusus di database (sebagai "Bad Setups").
*   Pada saat siklus pelatihan ulang, setup yang memiliki riwayat *loss* ini akan diberikan **bobot penalti** (misal: `sample_weight = 0.1` atau nilai negatif pada fungsi *objective*), sehingga algoritma dipaksa untuk "kapok" dan belajar menghindari konfigurasi setup tersebut di masa depan.

## 3. Parameter Manajemen Risiko Statis (Static Risk Management)

**Status Saat Ini (Debt):**
*   **`MAX_RISK_DOLLARS`**: Risiko kerugian dipatok rata dengan angka statis (meskipun sekarang sudah dihubungkan dengan *Streamlit widget*, sistem utamanya masih belum bisa menyesuaikan *scaling* ukuran akun secara otomatis berbanding *volatility*).
*   **`MAX_PYRAMIDING`**: Secara kaku dipatok maksimal 3 lapis eksekusi, terlepas dari apakah market sedang mengalami tren masif atau sedang berfluktuasi datar (*ranging/choppy*).

**Rencana Solusi:**
*   Mengimplementasikan varian **Kelly Criterion** di mana risiko akan dinaik-turunkan secara persentase mengikuti seberapa tinggi *win rate* dan seberapa besar ekuitas tersisa.
*   Mengubah `MAX_PYRAMIDING` agar dinamis mengikuti indikator kekuatan tren (seperti ADX). Jika ADX menunjukkan kekuatan tren tinggi, batas *pyramiding* diperlonggar.

## 4. Algoritma Eksekusi dan Circuit Breaker Statis

**Status Saat Ini (Debt):**
*   **Take Profit Tetap (RR 1:2)**: Model selalu melikuidasi penuh saat target RR 1:2 tercapai (Mode *Hit & Run*). Ini tidak optimal jika volatilitas mendadak menyempit atau melebar tajam.
*   **Spread Limit Tetap (400 poin)**: Batas *spread* kaku di 400 poin berbahaya jika berganti instrumen (*pair*) dengan standar *spread* yang jauh berbeda, dan juga tidak bisa beradaptasi dengan rata-rata pelebaran spread saat jam transaksi tertentu.
*   **Multiplier Anomali Volatilitas (3x ATR)**: Filter pencegah eksekusi yang dipatok kaku di saat range *candle* terakhir lebih dari 3x ATR-14.

**Rencana Solusi:**
*   **Dinamika RR**: Multiplier *Take Profit* (saat ini statis `2.0`) diubah agar adaptif mengikuti penyempitan dan pelebaran ATR *real-time*.
*   **Adaptive Spread Limit**: Mengubah `SPREAD_LIMIT_POINTS` menjadi `avg_spread_m1 * multiplier_dinamis`.
*   Memberikan ruang pada *logic exit* dan *entry blocker* agar beradaptasi dengan kondisi volatilitas terkini tanpa perlu menunggu siklus *retraining*.
