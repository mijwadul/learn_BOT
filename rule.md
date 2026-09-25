# Panduan Komprehensif Kaedah & Aturan BBMA (Oma Ally)

Dokumen ini merangkum seluruh aturan, hukum asas, topografi indikator, serta kaedah eksekusi dari sistem **BBMA Oma Ally** berdasarkan referensi resmi file `BBMA.pdf`. Sistem ini menjadi pedoman utama logika matematis dan model Machine Learning dalam Trading BOT.

---

## 1. Komponen & Parameter Indikator

BBMA menggunakan kombinasi unik dari Bollinger Bands, Linear Weighted Moving Average (LWMA), Simple Moving Average (SMA), dan Exponential Moving Average (EMA):

| No | Indikator | Periode | Metode / Apply to | Fungsi Utama |
|---|---|---|---|---|
| 1 | **Bollinger Bands** | 20, Deviasi 2 | Simple / Close | Mengukur volatilitas, batas range harga, dan deteksi momentum/sideways |
| 2 | **MA 5 High** | 5 | Linear Weighted (LWMA) / High | Batas tertinggi pencarian setup Re-entry Sell |
| 3 | **MA 10 High** | 10 | Linear Weighted (LWMA) / High | Konfirmasi zona Re-entry Sell |
| 4 | **MA 5 Low** | 5 | Linear Weighted (LWMA) / Low | Batas terendah pencarian setup Re-entry Buy |
| 5 | **MA 10 Low** | 10 | Linear Weighted (LWMA) / Low | Konfirmasi zona Re-entry Buy |
| 6 | **Mid BB** | 20 | Simple Moving Average (SMA) | Pemisah tren jangka menengah & batas penolakan body (*rejection*) |
| 7 | **EMA 50** | 50 | Exponential / Close | Penentu tren utama (*Major Trend*) & filter Zon Zero Loss |

---

## 2. Hukum Asas BBMA Oma Ally

Terdapat 2 hukum dasar yang tidak boleh dilanggar dalam pergerakan pasar:

1. **Hukum Moving Average terhadap Bollinger Bands:**
   * Moving Average (MA 5 / MA 10) **tidak boleh keluar** dari Bollinger Bands.
   * Apabila MA 5 atau MA 10 menembus keluar dari garis Bollinger Bands, maka pergerakan harga berada dalam kondisi **EXTREM** (sinyal awal pasar jenuh / potensi pembalikan arah).

2. **Hukum Candlestick terhadap Bollinger Bands:**
   * Candlestick **tidak boleh ditutup (Close) di luar** garis Bollinger Bands (Top BB atau Low BB).
   * Apabila candlestick ditutup di luar garis Bollinger Bands, maka candlestick tersebut dinamakan **Candlestick Momentum (CSM)** yang menandakan pergerakan tren berlanjut dengan kuat.

---

## 3. Topografi & Anatomi Sinyal BBMA

### A. EXTREM (Sinyal Awal Reversal / Pelemahan Tren)
* **Karakteristik Extrem Buy:**
  1. MA 5 Low keluar menembus ke bawah garis Low BB.
  2. Candlestick ditutup di luar Low BB lalu membentuk candlestick pembalikan (*reversal candle*).
  3. Terjadi *re-test* candle yang gagal membuat titik terendah baru.
* **Karakteristik Extrem Sell:**
  1. MA 5 High keluar menembus ke atas garis Top BB.
  2. Candlestick ditutup di luar Top BB lalu membentuk candlestick pembalikan.
  3. Terjadi *re-test* candle yang gagal membuat titik tertinggi baru.
* **Tindakan Pasca Extrem:** Wajib melakukan **Take Profit Wajib (TPW)** pada MA 5/10 berlawanan atau di Mid BB. Jangan menahan posisi melawan tren utama terlalu lama.

---

### B. MHV (Market Hilang Volume)
* Berlaku **selepas terjadinya Extrem dan TP Wajib**.
* **Ciri Khas:** Harga mencoba melanjutkan tren sebelumnya, namun **gagal menembus kembali Top BB atau Low BB**.
* Candlestick hanya mampu menyentuh Top/Low BB lalu ditutup kembali ke dalam (*rejection*).
* MHV menandakan bahwa kekuatan dorongan pasar sebelumnya telah habis (volume hilang).
* **Catatan Penting:** Setup MHV batal sekiranya terbentuk Candlestick Momentum (CSM) baru yang menembus Top/Low BB.

---

### C. CSA & CSAK (Candlestick Arah & Candlestick Arah Kukuh)
* **Candlestick Arah (CSA):**
  * Candlestick yang ditutup menembus garis MA 5 dan MA 10 (sinyal awal perubahan arah jangka pendek).
* **Candlestick Arah Kukuh (CSAK - Slide 31):**
  * Sinyal konfirmasi bahwa arah tren baru telah sah dan kuat.
  * **CSAK Buy:** Candlestick dibuka (Open) di bawah Mid BB dan ditutup (Close) **menembus ke atas Mid BB serta di atas MA 5/10 High**.
  * **CSAK Sell:** Candlestick dibuka (Open) di atas Mid BB dan ditutup (Close) **menembus ke bawah Mid BB serta di bawah MA 5/10 Low**.
* **Peran CSAK:** Menjadi syarat mutlak sebelum mencari setup Re-entry berikutnya.

---

### D. CSM (Candlestick Momentum - Slide 20 & 38)
* Candlestick yang **Close di luar Bollinger Bands**:
  * **CSM Buy:** Candle Close di atas Top BB saat Bollinger Bands mulai mengembang.
  * **CSM Sell:** Candle Close di bawah Low BB saat Bollinger Bands mulai mengembang.
* **Kaidah:** Dilarang keras membuka posisi counter-trend saat CSM sedang aktif. Tunggu hingga momentum mereda dan harga kembali melakukan *pullback* (Re-entry).

---

## 4. Setup RE-ENTRY (Setup Emas / Golden Setup)

Setup Re-entry adalah peluang entry paling aman dan paling menguntungkan dalam metode BBMA (Slide 20, 21, dan 33).

### A. Syarat Mutlak Keabsahan Re-entry (Slide 20-21)
1. **Pemicu Sebelumnya:** Re-entry **HANYA SAH** jika didahului oleh **CSAK** atau **CSM**. Re-entry tanpa CSAK/CSM dianggap tidak memiliki volume pendukung.
2. **Zona Entry:**
   * **Buy Re-entry:** Harga harus menguji (*pullback*) ke zona antara **MA 5 Low** dan **MA 10 Low** (`low <= max(LWMA_5_Low, LWMA_10_Low)`).
   * **Sell Re-entry:** Harga harus menguji (*pullback*) ke zona antara **MA 5 High** dan **MA 10 High** (`high >= min(LWMA_5_High, LWMA_10_High)`).

### B. Kaedah Penolakan Body / Body Rejection (Slide 33)
* **Re-entry Buy:**
  * Ekor candlestick (*wick*) boleh menembus zona MA 5/10 Low atau Mid BB.
  * Namun, **Body / Close candlestick TIDAK BOLEH ditutup di bawah Mid BB** (`close >= SMA_20`).
  * Candlestick Re-entry **TIDAK BOLEH ditutup di atas Top BB** (tidak boleh langsung membentuk CSM baru).
* **Re-entry Sell:**
  * Ekor candlestick boleh menembus zona MA 5/10 High atau Mid BB.
  * Namun, **Body / Close candlestick TIDAK BOLEH ditutup di atas Mid BB** (`close <= SMA_20`).
  * Candlestick Re-entry **TIDAK BOLEH ditutup di bawah Low BB**.

---

## 5. ZON ZERO LOSS (ZZL - Slide 51-56)

Zon Zero Loss adalah setup dengan probabilitas dan **Win Rate tertinggi** di dalam kaedah BBMA Oma Ally. Setup ini terjadi ketika seluruh hierarki indikator selaras searah tren besar.

### A. Zon Zero Loss BUY
1. **Hierarki Tren:** Mid BB berada di atas EMA 50 (`SMA_20 >= EMA_50`).
2. **Posisi Candlestick:** Seluruh candlestick atau titik Close candle berada di atas EMA 50 (`Close >= EMA_50`).
3. **Zona MA:** MA 5/10 Low berada di atas Mid BB atau di atas EMA 50.
4. **Eksekusi:** Candlestick melakukan *retracement* menyentuh zona MA 5/10 Low dan ditutup di atas Mid BB / EMA 50.
5. **Syarat Batal:** ZZL Buy batal sekiranya candlestick ditutup (*Close*) di bawah EMA 50.

### B. Zon Zero Loss SELL
1. **Hierarki Tren:** Mid BB berada di bawah EMA 50 (`SMA_20 <= EMA_50`).
2. **Posisi Candlestick:** Seluruh candlestick atau titik Close candle berada di bawah EMA 50 (`Close <= EMA_50`).
3. **Zona MA:** MA 5/10 High berada di bawah Mid BB atau di bawah EMA 50.
4. **Eksekusi:** Candlestick melakukan *retracement* menyentuh zona MA 5/10 High dan ditutup di bawah Mid BB / EMA 50.
5. **Syarat Batal:** ZZL Sell batal sekiranya candlestick ditutup (*Close*) di atas EMA 50.

---

## 6. Siklus Perjalanan Harga BBMA (Full Cycle)

Harga bergerak mengikuti pola siklus berulang yang teratur:

```
[ EXTREM ]
    ↓
[ TP WAJIB (TPW) ]
    ↓
[ MHV (Market Hilang Volume) ]
    ↓
[ CSA / CSAK (Arah Tren Baru) ]
    ↓
[ RE-ENTRY 1 ]  <-- Titik Entry Terbaik (Risk Reward Optimal)
    ↓
[ CSM (Momentum Berlanjut) ]
    ↓
[ RE-ENTRY 2 / 3 ]
    ↓
[ EXTREM Baru ]  <-- Siklus berulang ke arah sebaliknya
```

---

## 7. Pemetaan ke dalam Arsitektur Trading BOT

Seluruh aturan di atas diterjemahkan ke dalam komponen algoritma bot:

| Modul Codebase | Implementasi Aturan BBMA |
|---|---|
| `backend/utils/indicators.py` | Perhitungan matematis LWMA 5/10 (High & Low), Bollinger Bands, EMA 50, deteksi CSM, Extrem, CSAK, dan status Zon Zero Loss. |
| `backend/agents/research/target_labeler.py` | Pelabelan target pelatihan berbasis Triple Barrier Method di level LWMA dengan aturan Body Rejection (Slide 33) & Zon Zero Loss (Slide 51-56). |
| `backend/agents/researcher.py` | Filter kandidat dataset pelatihan, eliminasi data *noise*, dan kalibrasi Optuna dengan bobot seimbang (*balanced*). |
| `backend/agents/gatekeeper.py` | Validasi Out-Of-Sample (OOS) yang menguji keabsahan sinyal murni berdasarkan aturan Re-entry BBMA dan threshold keyakinan AI. |
| `backend/agents/executor.py` | Eksekutor live order dengan sekring *Body Rejection*, *No-CSM Filter*, dan proteksi pembatalan order jika harga menembus EMA 50. |
