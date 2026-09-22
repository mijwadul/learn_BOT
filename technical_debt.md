# 🛠️ Technical Debt & Roadmap Evolusi Arsitektur

Dokumen ini mencatat *Technical Debt* (hutang teknis) yang tersisa setelah perombakan arsitektur besar-besaran (MTF H1/H4, Optuna, dan RLHF) berhasil diterapkan. 

Demi efisiensi (*menghindari kerja dua kali untuk membangun antarmuka*), urutan pengerjaan *roadmap* ini disusun dengan mendahulukan **Migrasi Infrastruktur**, barulah dilanjutkan dengan **Penambahan Fitur Logika AI**.

---

## FASE 1: Migrasi Infrastruktur (Fullstack FastAPI + Next.js)

**Status Saat Ini (Debt):**
Framework *Streamlit* (`app.py`) mengeksekusi ulang seluruh *script* Python secara sinkron setiap kali ada interaksi antarmuka. Proses merender *Plotly chart* yang kompleks menyita banyak tenaga CPU. Membangun fitur rumit di dalam *Streamlit* saat ini hanya akan berujung pada penghapusan kode secara sia-sia di masa depan.

**Rencana Solusi:**
*   **Backend Terpisah (FastAPI):** Kode Python (`app.py`) diubah murni menjadi *REST API* dan *WebSocket* menggunakan `FastAPI`. Sistem Python berjalan 100% di latar belakang yang berfokus penuh pada koneksi MT5, *Database*, dan kalkulasi AI.
*   **Frontend Modern (Next.js):** Membangun *dashboard* UI baru menggunakan Next.js dengan struktur *Sidebar Navigation* bepedoman pada ai trading dashboard
    1.  **Dashboard:** Memuat saklar "LIVE/IDLE" dan grafik *candlestick* mulus (TradingView Charts) berbasis *real-time tick* (WebSocket).
    2.  **Database:** Eksekusi *Force Backfill* dan manajemen tabel.
    3.  **Strategies:** Ruang kendali laboratorium AI.
    4.  **Logs:** Jendela terminal *real-time* yang menarik *stream* teks langsung dari *backend* Python.
*   **Mobile-Friendly (Responsive PWA):** Antarmuka dibangun dengan *Tailwind CSS*. Pada layar *smartphone*, UI beradaptasi secara elegan (menjadi *Hamburger Menu*), memungkinkan kontrol *Emergency Stop* darimana saja.
*   **Dampak Akhir:** Membebaskan ruang komputasi CPU dan RAM secara masif, serta menyiapkan pondasi antarmuka yang solid untuk Fase 2 dan 3.

---

## FASE 2: Pemisahan Total Pelatihan (Decoupled Training Pipeline)

**Status Saat Ini (Debt):**
Proses pelatihan AI masih berada di dalam satu siklus yang sama (Dual-Target). Jika Mode Normal gagal dan Mode Runner lulus OOS, sistem tetap memuat ulang jutaan baris data secara menyeluruh untuk melakukan "remedial". Ini sangat boros waktu dan RAM.

**Rencana Solusi:**
*   **Pemisahan Fungsi:** Memecah fungsi `train_models` di `researcher.py` menjadi `train_normal_mode()` dan `train_runner_mode()`.
*   **Isolasi Dataset:** Mode Normal (Scalping) tidak akan dimuati fitur kompleks H4, menghemat memori drastis.
*   **Hyperparameter Terpisah:** Menyesuaikan ruang pencarian *Optuna* secara spesifik berdasarkan mode.
*   **Retraining Independen:** Jika mode Normal gagal, sistem hanya akan meremedial mode Normal tanpa menyentuh model Runner, memangkas waktu *training* hingga 50%.

---

## FASE 3: Eksekusi Independen (Partial & Forced Live Mode)

**Status Saat Ini (Debt):**
Sistem bersifat kaku (*All-or-Nothing*). Jika salah satu mode dikarantina, maka seluruh operasi *trading bot* akan berhenti total.

**Rencana Solusi:**
*   **Auto-Fallback (Live Sebagian):** `supervisor.py` tidak akan mematikan sistem. Bot tetap menembak di pasar menggunakan mode yang lulus OOS, sementara mode yang gagal diremedial di latar belakang.
*   **Manual Override (Forced Live):** Melalui UI Next.js (Fase 1), pengguna dapat memunculkan *custom combobox* untuk memaksa bot mengaktifkan mode tertentu meskipun mode tersebut gagal OOS.
*   **Isolated Circuit Breaker:** Meskipun dijalankan secara paksa, *Circuit Breaker* tetap aktif secara terisolasi. Mode yang merugi parah akan diputus otomatis tanpa mematikan mesin utama.
