# 🤖 BBMA Autonomous AI Trader (Enterprise Quant Edition)

Sistem *algorithmic trading* otonom berbasis *Agentic Workflow* dan *Tree-Based Machine Learning* (LightGBM/XGBoost). Bot ini melakukan pencarian pola probabilitas secara mandiri menggunakan topografi BBMA MTF, mengintegrasikan kalender ekonomi, dan dilengkapi dengan *Circuit Breakers* absolut untuk melindungi modal dari anomali pasar fisik.

## 🏗️ Arsitektur Sistem (The 5-Agent Crew)

*   **Agent 0: The Supervisor (Orchestrator & State Machine)**
    *   Mengatur transisi fase operasional (Ingesti Data, Riset, Evaluasi, Live).
    *   **[SEKRING] The Friday Liquidator:** Protokol penutup posisi terbuka otomatis tepat 1x setiap Sabtu pukul 00:00 WIB untuk instrumen non-crypto (Forex/Gold) guna mengeliminasi risiko gap akhir pekan. Instrumen crypto (BTCUSD) dikecualikan dan fungsi trading tetap berjalan normal selama akhir pekan.
    *   **[SEKRING] Max Drawdown Reset:** Mengembalikan sistem ke mode Riset (Karantina) secara otomatis JIKA kerugian akumulatif menembus batas mutlak **30% dari total ekuitas**.

*   **Agent 1: Data Miner (Database & Feature Engineer)**
    *   **Infrastruktur:** Menarik data dari MT5 API ke *Database* lokal (PostgreSQL/SQLite) dan mendukung injeksi CSV manual.
    *   **Anti-Leakage MTF Merging:** Menyatukan data M15, M5, dan M1 menggunakan `ffill` dan `shift(1)` untuk mengeliminasi *Data Leakage*.
    *   **Topografi BBMA (Parameter Paten):** 
        *   Bollinger Bands (20, 2)
        *   EMA (50, Close)
        *   LWMA High (5 dan 10, High)
        *   LWMA Low (5 dan 10, Low)
    *   **Macro Intelligence:** Menerjemahkan API Kalender Ekonomi menjadi kolom *countdown* menit menuju rilis berita "High Impact".

*   **Agent 2: The Researcher (Dual-Target AI Brain)**
    *   Melatih algoritma (LightGBM) menggunakan target dinamis berbasis volatilitas (ATR/Lebar BB).
    *   Memprediksi 2 Kunci Jawaban Probabilitas secara simultan:
        1.  `Target_Normal`: Probabilitas mencapai profit RR 1:2.
        2.  `Target_Runner`: Probabilitas tren masif mencapai profit RR 1:5 ke atas.

*   **Agent 3: The Gatekeeper (Out-of-Sample Validator)**
    *   Menolak model yang terindikasi *overfitting* melalui *Walk-Forward Backtest* pada porsi data yang disembunyikan (*Out-of-Sample*).

*   **Agent 4: The Executor (Context-Aware Risk Manager)**
    *   Mengeksekusi orde di M1 dengan kalkulasi Lot mutlak: `Lot = Max_Risk_$ / (Jarak_SL_Dinamis * Poin_Value)`.
    *   **[SEKRING] Pre-Trade Execution Filter:** Blokir eksekusi JIKA *Spread* melampaui **400 poin** atau lonjakan volatilitas tak wajar (anomali *tick*).
    *   **[SEKRING] Disaster Recovery TP:** Menempatkan *Hard Take Profit* 1:10 di server broker sebagai jaring pengaman mati listrik/koneksi.
    *   **Protokol Eksekusi Dinamis:**
        *   *Mode Hit & Run (Probabilitas Tren Rendah):* Menutup 100% posisi saat menyentuh RR 1:2.
        *   *Mode Trend Rider (Probabilitas Tren Tinggi):* Saat mencapai RR 1:2, melakukan **Partial Close 50% lot**, memindahkan sisa posisi ke *Break Even* (BE), lalu menggunakan EMA 50 / WMA 10 sebagai *Trailing Stop* untuk menangkap tren panjang.

## 🔄 Siklus Operasional Autopilot
1.  **[DATA INGESTION]** Tarik *candle* MT5 & *event* makro, perbarui DB, hitung fitur teknikal.
2.  **[INCUBATOR]** Latih probabilitas *Dual-Target* pada topografi terbaru.
3.  **[EVALUATION]** Uji *Walk-Forward Backtest*. Lulus = Produksi; Gagal = Ulangi Riset.
4.  **[LIVE TRADING]** Evaluasi probabilitas M1, validasi sekring (*Spread* < 400), hitung Lot mutlak, eksekusi order.
5.  **[SELF-CORRECTION]** Jika *drawdown* harian menyentuh -30%, kembalikan sistem ke tahap [INCUBATOR].

## 🖥️ Command Center (Next.js & FastAPI Institutional UI)
*   **Master Controls:** Start, Emergency Stop, Multi-Pair Activation, Otak (Brain) Switcher.
*   **Risk Setup:** Input toleransi batas rugi per transaksi ($), dynamic lot sizing.
*   **System Health:** Ping MT5, Status Database PostgreSQL, Multi-Pair Health.
*   **Live Metrics:** Dual-Target Probabilities, Market Regime (ADX), Capital Growth, Active Fuses.
*   **Terminal Log:** Streaming WebSocket real-time untuk komunikasi antar-agen dan laporan pemblokiran (misal: *"Eksekusi ditolak: Spread 410 poin"*).