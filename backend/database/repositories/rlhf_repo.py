import datetime
import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..connection import sync_engine
from ..models.rlhf import ApprovedSetup, RejectedSetup, IgnoredSetup, HardNegative
from ..migrations import ensure_schema_migrations

def save_approved_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = "", mode: str = "normal"):
    """Simpan ID setup yang telah disetujui trader ke approved_setups (dipisahkan per mode)."""
    try:
        ensure_schema_migrations()
        mode_val = mode.lower() if mode else "normal"
        with Session(sync_engine) as session:
            existing = session.query(ApprovedSetup).filter(
                ApprovedSetup.setup_id == str(setup_id),
                ApprovedSetup.mode == mode_val
            ).first()
            if not existing:
                setup = ApprovedSetup(
                    setup_id=str(setup_id),
                    mode=mode_val,
                    symbol=str(symbol),
                    action=str(action),
                    probability=float(probability),
                    approved_at=datetime.datetime.now(),
                    notes=str(notes) if notes else f"Approved ({mode_val}) by Trader via RLHF"
                )
                session.add(setup)
                session.commit()
                return True
        return False
    except Exception as e:
        logging.error(f"Failed to save approved setup: {e}")
        return False

def get_approved_setup_ids(mode: str = None):
    """Ambil himpunan ID setup yang telah di-approve manusia untuk pembobotan LightGBM (opsional per mode)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            if mode:
                rows = session.query(ApprovedSetup.setup_id).filter(ApprovedSetup.mode == mode.lower()).all()
            else:
                rows = session.query(ApprovedSetup.setup_id).all()
            return {r[0] for r in rows}
    except Exception as e:
        logging.error(f"Failed to get approved setup IDs: {e}")
        return set()

def get_all_approved_setups(mode: str = None):
    """Ambil seluruh data approved setups dalam bentuk DataFrame (opsional per mode)."""
    try:
        ensure_schema_migrations()
        where_sql = f"WHERE mode = '{mode.lower()}'" if mode else ""
        query = f"SELECT id, setup_id, mode, symbol, action, probability, approved_at, notes FROM approved_setups {where_sql} ORDER BY approved_at DESC"
        return pd.read_sql(query, con=sync_engine)
    except Exception as e:
        logging.error(f"Failed to query approved setups: {e}")
        return pd.DataFrame()

def save_rejected_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = "", mode: str = "normal"):
    """Simpan ID setup yang telah ditolak trader ke rejected_setups (dipisahkan per mode)."""
    try:
        ensure_schema_migrations()
        mode_val = mode.lower() if mode else "normal"
        with Session(sync_engine) as session:
            existing = session.query(RejectedSetup).filter(
                RejectedSetup.setup_id == str(setup_id),
                RejectedSetup.mode == mode_val
            ).first()
            if not existing:
                setup = RejectedSetup(
                    setup_id=str(setup_id),
                    mode=mode_val,
                    symbol=str(symbol),
                    action=str(action),
                    probability=float(probability),
                    rejected_at=datetime.datetime.now(),
                    notes=str(notes) if notes else f"Rejected ({mode_val}) by Trader via RLHF"
                )
                session.add(setup)
                session.commit()
                return True
        return False
    except Exception as e:
        logging.error(f"Failed to save rejected setup: {e}")
        return False

def get_rejected_setup_ids(mode: str = None):
    """Ambil himpunan ID setup yang telah di-reject manusia untuk penalty LightGBM (opsional per mode)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            if mode:
                rows = session.query(RejectedSetup.setup_id).filter(RejectedSetup.mode == mode.lower()).all()
            else:
                rows = session.query(RejectedSetup.setup_id).all()
            return {r[0] for r in rows}
    except Exception as e:
        logging.error(f"Failed to get rejected setup IDs: {e}")
        return set()

def save_ignored_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = "", mode: str = "normal"):
    """Simpan ID setup yang sengaja diabaikan trader ke ignored_setups (dipisahkan per mode)."""
    try:
        ensure_schema_migrations()
        mode_val = mode.lower() if mode else "normal"
        with Session(sync_engine) as session:
            existing = session.query(IgnoredSetup).filter(
                IgnoredSetup.setup_id == str(setup_id),
                IgnoredSetup.mode == mode_val
            ).first()
            if not existing:
                setup = IgnoredSetup(
                    setup_id=str(setup_id),
                    mode=mode_val,
                    symbol=str(symbol),
                    action=str(action),
                    probability=float(probability),
                    ignored_at=datetime.datetime.now(),
                    notes=str(notes) if notes else f"Ignored ({mode_val}) by Trader via RLHF — Outcome dianggap noise"
                )
                session.add(setup)
                session.commit()
                return True
        return False
    except Exception as e:
        logging.error(f"Failed to save ignored setup: {e}")
        return False

def get_ignored_setup_ids(mode: str = None):
    """Ambil himpunan ID setup yang sengaja diabaikan trader (opsional per mode)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            if mode:
                rows = session.query(IgnoredSetup.setup_id).filter(IgnoredSetup.mode == mode.lower()).all()
            else:
                rows = session.query(IgnoredSetup.setup_id).all()
            return {r[0] for r in rows}
    except Exception as e:
        logging.error(f"Failed to get ignored setup IDs: {e}")
        return set()

def add_hard_negative(setup_id: str, failed_mode: str = "Normal"):
    try:
        with Session(sync_engine) as session:
            existing = session.query(HardNegative).filter_by(setup_id=setup_id).first()
            if not existing:
                new_hn = HardNegative(setup_id=setup_id, failed_mode=failed_mode)
                session.add(new_hn)
                session.commit()
                return True
    except Exception as e:
        logging.error(f"Gagal menyimpan Hard Negative: {e}")
    return False

def bulk_add_hard_negatives(records: list):
    """records adalah list of dict: [{'setup_id': '...', 'failed_mode': '...'}, ...]"""
    try:
        with Session(sync_engine) as session:
            existing_df = pd.read_sql("SELECT setup_id FROM hard_negatives", con=sync_engine)
            existing_ids = set(existing_df['setup_id'].tolist()) if not existing_df.empty else set()
            
            new_objects = []
            for r in records:
                if r['setup_id'] not in existing_ids:
                    new_objects.append(HardNegative(setup_id=r['setup_id'], failed_mode=r['failed_mode']))
                    existing_ids.add(r['setup_id'])
            
            if new_objects:
                session.bulk_save_objects(new_objects)
                session.commit()
                return len(new_objects)
            return 0
    except Exception as e:
        logging.error(f"Gagal menyimpan Hard Negatives (Bulk): {e}")
        return 0

def get_hard_negative_ids(mode: str = None):
    try:
        ensure_schema_migrations()
        if mode:
            query = f"SELECT setup_id FROM hard_negatives WHERE LOWER(failed_mode) = '{mode.lower()}'"
        else:
            query = "SELECT setup_id FROM hard_negatives"
        df = pd.read_sql(query, con=sync_engine)
        return df['setup_id'].tolist() if not df.empty else []
    except Exception:
        return []

def reset_ai_trade_history(categories: list = None):
    """
    Menghapus catatan hasil trading AI berdasarkan kategori pilihan untuk persiapan fresh start.
    Kategori yang didukung:
    - 'trade_logs': Riwayat Transaksi & Catatan PnL (tabel trade_logs)
    - 'decision_samples': Sampel Keputusan & Feature Vector Live AI (tabel live_decision_samples)
    - 'journal': Catatan Kronologis Black Box Journal (tabel trade_journal)
    - 'rlhf_setups': Label & Feedback Trader Manual (tabel approved_setups, rejected_setups, ignored_setups)
    - 'hard_negatives': Hard Negative Error Samples (tabel hard_negatives)
    """
    category_map = {
        "trade_logs": ["trade_logs"],
        "decision_samples": ["live_decision_samples"],
        "journal": ["trade_journal"],
        "rlhf_setups": ["approved_setups", "rejected_setups", "ignored_setups"],
        "hard_negatives": ["hard_negatives"],
    }
    
    if not categories or "all" in categories:
        tables = [
            "trade_logs",
            "live_decision_samples",
            "trade_journal",
            "approved_setups",
            "rejected_setups",
            "ignored_setups",
            "hard_negatives"
        ]
    else:
        tables = []
        for cat in categories:
            if cat in category_map:
                tables.extend(category_map[cat])
            elif cat in [
                "trade_logs", "live_decision_samples", "trade_journal", 
                "approved_setups", "rejected_setups", "ignored_setups", "hard_negatives"
            ]:
                tables.append(cat)
                
    tables = list(dict.fromkeys(tables))

    cleared_counts = {}
    with sync_engine.begin() as conn:
        for tbl in tables:
            try:
                count_res = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
                conn.execute(text(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE"))
                cleared_counts[tbl] = count_res
            except Exception:
                try:
                    conn.execute(text(f"DELETE FROM {tbl}"))
                    cleared_counts[tbl] = "cleared"
                except Exception as e2:
                    cleared_counts[tbl] = f"error: {e2}"
    logging.info(f"✅ [Fresh Start] Tabel yang dibersihkan: {cleared_counts}")
    return cleared_counts
