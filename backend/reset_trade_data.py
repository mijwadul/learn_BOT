"""
Script CLI untuk me-reset/drop seluruh catatan riwayat trading AI:
- trade_logs
- live_decision_samples
- trade_journal
- approved_setups, rejected_setups, ignored_setups
- hard_negatives

Menjaga data candlestick (market_data_merged & economic_events) tetap utuh.
Jalankan script ini sebelum memulai trading fresh start di akun cent baru:
    python backend/reset_trade_data.py
"""

import sys
import os

# Tambahkan direktori backend ke path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import reset_ai_trade_history

def main():
    print("==================================================")
    print("   FRESH START: RESET RIWAYAT TRADING BOT AI      ")
    print("==================================================")
    print("Membersihkan tabel catatan transaksi & sampel AI...")
    
    result = reset_ai_trade_history()
    
    print("\nRincian data yang dibersihkan:")
    for table, count in result.items():
        print(f"  - {table:<25}: {count} baris dihapus")
        
    print("\n✅ Database siap digunakan untuk Fresh Start akun baru!")
    print("==================================================")

if __name__ == "__main__":
    main()
