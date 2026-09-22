# 🛠️ Technical Debt & Rencana Arsitektur (Roadmap)

Dokumen ini mencatat *Technical Debt* (hutang teknis) yang tersisa setelah perombakan arsitektur besar-besaran (MTF H1/H4, Optuna, dan RLHF) berhasil diterapkan. 

## 1. Pemisahan Total Pelatihan (Training Pipeline) Mode Normal & Mode Runner

**Status Saat Ini (Debt):**
Saat ini, model evaluasi kita sudah cerdas membedakan target "Normal" (Scalping) dan "Runner" (Trend Following). Namun, proses pelatihannya (*training pipeline*) masih berada di dalam satu siklus yang sama (Dual-Target). 
Buktinya, ketika Mode Normal gagal dan Mode Runner lulus, sistem tetap memuat ulang jutaan baris data secara menyeluruh untuk melakukan "remedial". Ini sangat menguras tenaga prosesor dan menuntut kapasitas RAM yang masif (hingga 10GB+), serta memakan waktu yang lama karena siklus tidak dipisah secara independen.

**Rencana Solusi (Decoupled Training Pipeline):**
*   **Pemisahan Fungsi Pelatihan:** Memecah fungsi `train_models` di `researcher.py` menjadi dua fungsi yang independen: `train_normal_mode()` dan `train_runner_mode()`.
*   **Isolasi Dataset (Optimasi RAM):** Mengklasifikasikan asupan data berdasarkan mode. Mode Normal (Scalping M1/M5) mungkin tidak memerlukan fitur kompleks dari H4, sehingga kita bisa memangkas beban memori secara drastis saat melatih Mode Normal.
*   **Hyperparameter Search Space Terpisah:** Menyesuaikan jangkauan pencarian *Optuna* berdasarkan mode. (Misal: Mode Normal dipaksa menggunakan *tree* yang lebih dangkal agar tidak menghafal *noise* pasar).
*   **Retraining Independen:** Jika AI mendeteksi mode Normal gagal di masa depan, ia **hanya** akan memuat ulang data yang relevan untuk Normal dan melatih model Normal saja, tanpa mengganggu model Runner yang sudah berjalan optimal. Ini akan memangkas waktu *retraining* hingga 50%!

## 2. Fitur Eksekusi Independen (Partial & Forced Live Mode)

**Status Saat Ini (Debt):**
Saat ini, sistem bersifat "All-or-Nothing". Jika salah satu mode (misalnya Normal) masuk ke fase karantina (retraining) akibat gagal uji OOS atau terkena *Circuit Breaker*, maka **seluruh bot akan berhenti bertrading**. Padahal, mode Runner mungkin lulus OOS dan sedang sangat *profitable* untuk dieksekusi di market *live*.

**Rencana Solusi (Partial & Forced Live Mode):**
*   **Auto-Fallback to Passed Mode (Live Sebagian):** Jika salah satu mode dikarantina, `supervisor.py` tidak akan mematikan sistem secara total. Bot akan tetap *live* di pasar menggunakan mode yang sehat (lulus OOS), sementara mode yang sakit akan dikarantina dan dilatih ulang di latar belakang (Background Retraining).
*   **Manual Override (Forced Live):** Menambahkan saklar khusus di Web UI yang memberi wewenang pada pengguna (User) untuk memaksa (*force start*) bot bertrading menggunakan mode tertentu, meskipun mode tersebut secara teori gagal uji OOS.
*   **Isolated Circuit Breaker:** Meskipun pengguna memaksa mode yang sakit untuk tetap *live*, sistem perlindungan *Circuit Breaker* (batas maksimal kerugian *drawdown*) akan tetap mengawasi secara independen dan otomatis memutus laju mode tersebut jika menembus batas kerugian brutal, menyelamatkan ekuitas akun Anda.
