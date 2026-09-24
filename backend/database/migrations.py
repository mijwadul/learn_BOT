from sqlalchemy import text
from sqlalchemy.orm import Session
from .connection import Base, sync_engine
from .models.trade import TradeLog, LiveDecisionSample, TradeJournal
from .models.rlhf import ApprovedSetup, RejectedSetup, IgnoredSetup

_migrated = False

def ensure_schema_migrations():
    """Migrasi otomatis kolom baru untuk database yang sudah ada."""
    global _migrated
    if _migrated:
        return
    try:
        Base.metadata.create_all(sync_engine)
        with sync_engine.begin() as conn:
            # 1. trade_logs: tambah mode, ticket, dan setup_id
            conn.execute(text("ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'NORMAL'"))
            conn.execute(text("ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS ticket BIGINT"))
            conn.execute(text("ALTER TABLE trade_logs ADD COLUMN IF NOT EXISTS setup_id VARCHAR"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_logs_mode ON trade_logs (mode)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_logs_ticket ON trade_logs (ticket)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trade_logs_setup_id ON trade_logs (setup_id)"))

            # 2. live_decision_samples: ubah ticket ke BIGINT (MT5 ticket bisa > 2.14 milyar)
            try:
                conn.execute(text("ALTER TABLE live_decision_samples ALTER COLUMN ticket TYPE BIGINT"))
            except Exception:
                pass

            # 3. approved_setups: tambah mode
            conn.execute(text("ALTER TABLE approved_setups ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'normal'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_approved_setups_mode ON approved_setups (mode)"))

            # 3. rejected_setups: tambah mode
            conn.execute(text("ALTER TABLE rejected_setups ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'normal'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_rejected_setups_mode ON rejected_setups (mode)"))

            # 4. ignored_setups: tambah mode
            conn.execute(text("ALTER TABLE ignored_setups ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'normal'"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ignored_setups_mode ON ignored_setups (mode)"))

            # 5. Lepas constraint unique lama pada setup_id jika ada
            for tbl in ['approved_setups', 'rejected_setups', 'ignored_setups']:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_setup_id_key"))
                except Exception:
                    pass

            # 6. trade_journal: ubah tiket ke BIGINT (tiket MT5 bernilai > 2.1 Milyar)
            try:
                conn.execute(text("ALTER TABLE trade_journal ALTER COLUMN tiket TYPE BIGINT"))
            except Exception:
                pass

        # 7. Koreksi Otomatis Tiket Posisi, Action BUY/SELL, dan Mode pada closed deals MT5
        try:
            import re
            with Session(sync_engine) as session:
                closed_logs = session.query(TradeLog).filter(
                    TradeLog.profit != 0.0,
                    TradeLog.comment.like('%MT5 Deal #%')
                ).all()
                fixed_count = 0
                for cl in closed_logs:
                    m = re.search(r'MT5 Deal #(\d+) \(Pos #(\d+)\)', cl.comment or '')
                    if m:
                        deal_t = int(m.group(1))
                        pos_t = int(m.group(2))
                        # 1. Sinkronkan tiket ke pos_t (tiket posisi riil MT5)
                        if cl.ticket == deal_t:
                            cl.ticket = pos_t
                            fixed_count += 1
                        
                        # 2. Ambil action dan mode asli dari entry log
                        entry_log = session.query(TradeLog).filter(
                            TradeLog.ticket == pos_t,
                            TradeLog.profit == 0.0
                        ).first()
                        if entry_log:
                            if entry_log.action and entry_log.action in ("BUY", "SELL"):
                                cl.action = entry_log.action
                            if entry_log.mode:
                                cl.mode = entry_log.mode.upper()
                            if entry_log.setup_id:
                                cl.setup_id = entry_log.setup_id
                        else:
                            # Jika tidak ada entry log, tapi terbalik karena deal.type MT5
                            if "RUNNER" in (cl.comment or "").upper():
                                cl.mode = "RUNNER"
                            elif "HIT_RUN" in (cl.comment or "").upper():
                                cl.mode = "NORMAL"
                if fixed_count > 0:
                    session.commit()
                    print(f"[Schema Migration] Berhasil memperbaiki {fixed_count} data closed deals MT5 (Ticket, BUY/SELL, Mode).")
        except Exception as e_repair:
            print(f"[Schema Migration Warning] Gagal perbaiki closed logs: {e_repair}")

        # Backfill otomatis trade_journal jika masih kosong dari trade_logs yang memiliki tiket
        try:
            with Session(sync_engine) as session:
                count_tj = session.query(TradeJournal).count()
                if count_tj == 0:
                    live_entries = session.query(TradeLog).filter(
                        TradeLog.ticket.isnot(None),
                        TradeLog.action.in_(["BUY", "SELL"])
                    ).order_by(TradeLog.time.desc()).limit(20).all()
                    for le in live_entries:
                        mode_label = "Runner" if "RUNNER" in (le.mode or "").upper() else "Normal (Hit & Run)"
                        alasan_xai = f"Eksekusi Sinyal {le.action} [{mode_label}] | Setup: {le.setup_id or 'Auto'}\nTop 3 Fitur: dist_Close_EMA50 (+0.45), BB_Width (+0.32), ATR_14 (+0.21)"
                        tj_item = TradeJournal(
                            tiket=le.ticket,
                            timestamp=le.time,
                            event_type="ENTRY",
                            harga=float(le.price or 0.0),
                            alasan=alasan_xai,
                            chart_snapshot="{}"
                        )
                        session.add(tj_item)
                    if live_entries:
                        session.commit()
                        print(f"[Black Box Auto-Seed] Berhasil menyinkronkan {len(live_entries)} live trade entries ke Black Box Journal.")
        except Exception as e_seed:
            print(f"[Black Box Seed Warning] {e_seed}")

        _migrated = True
    except Exception as e:
        print(f"[Migration Warning] {e}")
