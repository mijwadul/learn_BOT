import datetime
import logging
import pandas as pd
from sqlalchemy import text, func
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

def get_approved_setup_ids(mode: str = None, symbol: str = None):
    """Ambil himpunan ID setup yang telah di-approve manusia untuk pembobotan LightGBM (opsional per mode & symbol)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            query = session.query(ApprovedSetup.setup_id)
            if mode:
                query = query.filter(ApprovedSetup.mode == mode.lower())
            if symbol:
                query = query.filter(func.upper(ApprovedSetup.symbol) == symbol.upper())
            rows = query.all()
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
        with sync_engine.connect() as conn:
            return pd.read_sql(text(query), con=conn)
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

def get_rejected_setup_ids(mode: str = None, symbol: str = None):
    """Ambil himpunan ID setup yang telah di-reject manusia untuk penalty LightGBM (opsional per mode & symbol)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            query = session.query(RejectedSetup.setup_id)
            if mode:
                query = query.filter(RejectedSetup.mode == mode.lower())
            if symbol:
                query = query.filter(func.upper(RejectedSetup.symbol) == symbol.upper())
            rows = query.all()
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

def get_ignored_setup_ids(mode: str = None, symbol: str = None):
    """Ambil himpunan ID setup yang sengaja diabaikan trader (opsional per mode & symbol)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            query = session.query(IgnoredSetup.setup_id)
            if mode:
                query = query.filter(IgnoredSetup.mode == mode.lower())
            if symbol:
                query = query.filter(func.upper(IgnoredSetup.symbol) == symbol.upper())
            rows = query.all()
            return {r[0] for r in rows}
    except Exception as e:
        logging.error(f"Failed to get ignored setup IDs: {e}")
        return set()

def get_rlhf_curation_stats(symbol: str = None, mode: str = None):
    """Ambil statistik jumlah setup yang telah dikurasi (Approved, Rejected, Ignored) per mode dan simbol."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            q_app = session.query(func.count(ApprovedSetup.id))
            q_rej = session.query(func.count(RejectedSetup.id))
            q_ign = session.query(func.count(IgnoredSetup.id))
            if mode:
                q_app = q_app.filter(ApprovedSetup.mode == mode.lower())
                q_rej = q_rej.filter(RejectedSetup.mode == mode.lower())
                q_ign = q_ign.filter(IgnoredSetup.mode == mode.lower())
            if symbol:
                q_app = q_app.filter(func.upper(ApprovedSetup.symbol) == symbol.upper())
                q_rej = q_rej.filter(func.upper(RejectedSetup.symbol) == symbol.upper())
                q_ign = q_ign.filter(func.upper(IgnoredSetup.symbol) == symbol.upper())
            app_count = q_app.scalar() or 0
            rej_count = q_rej.scalar() or 0
            ign_count = q_ign.scalar() or 0
            return {
                "approved": app_count,
                "rejected": rej_count,
                "ignored": ign_count,
                "total_curated": app_count + rej_count + ign_count
            }
    except Exception as e:
        logging.error(f"Failed to get curation stats: {e}")
        return {"approved": 0, "rejected": 0, "ignored": 0, "total_curated": 0}

def add_hard_negative(setup_id: str, failed_mode: str = "Normal", symbol: str = "XAUUSD"):
    try:
        with Session(sync_engine) as session:
            existing = session.query(HardNegative).filter_by(setup_id=setup_id).first()
            if not existing:
                new_hn = HardNegative(setup_id=setup_id, failed_mode=failed_mode, symbol=str(symbol).upper())
                session.add(new_hn)
                session.commit()
                return True
    except Exception as e:
        logging.error(f"Gagal menyimpan Hard Negative: {e}")
    return False

def bulk_add_hard_negatives(records: list):
    """records adalah list of dict: [{'setup_id': '...', 'failed_mode': '...', 'symbol': '...'}, ...]"""
    try:
        with Session(sync_engine) as session:
            with sync_engine.connect() as conn:
                existing_df = pd.read_sql(text("SELECT setup_id FROM hard_negatives"), con=conn)
            existing_ids = set(existing_df['setup_id'].tolist()) if not existing_df.empty else set()
            
            new_objects = []
            for r in records:
                if r['setup_id'] not in existing_ids:
                    sym = str(r.get('symbol', 'XAUUSD')).upper()
                    new_objects.append(HardNegative(setup_id=r['setup_id'], failed_mode=r['failed_mode'], symbol=sym))
                    existing_ids.add(r['setup_id'])
            
            if new_objects:
                session.bulk_save_objects(new_objects)
                session.commit()
                return len(new_objects)
            return 0
    except Exception as e:
        logging.error(f"Gagal menyimpan Hard Negatives (Bulk): {e}")
        return 0

def get_hard_negative_ids(mode: str = None, symbol: str = None):
    try:
        ensure_schema_migrations()
        conditions = []
        if mode:
            conditions.append(f"LOWER(failed_mode) = '{mode.lower()}'")
        if symbol:
            conditions.append(f"UPPER(symbol) = '{symbol.upper()}'")
        where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"SELECT setup_id FROM hard_negatives {where_sql}"
        with sync_engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
        return df['setup_id'].tolist() if not df.empty else []
    except Exception as e:
        logging.error(f"Failed to fetch hard negative ids: {e}")
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
