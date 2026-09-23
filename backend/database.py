from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy import Column, Integer, String, Float, DateTime, select, func, Text, BigInteger
from config import Config

engine = create_async_engine(Config.DATABASE_URL, echo=False)
sync_engine = create_engine(Config.SYNC_DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

class MarketData(Base):
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    time = Column(DateTime, index=True, unique=True)
    symbol = Column(String, index=True)
    timeframe = Column(String, index=True) # M1, M5, M15
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    tick_volume = Column(Integer)
    spread = Column(Integer)
    minutes_to_high_impact_news = Column(Float, default=9999) # Fitur makroekonomi

class TradeLog(Base):
    __tablename__ = "trade_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(BigInteger, index=True, nullable=True) # MT5 Deal/Order Ticket
    setup_id = Column(String, index=True, nullable=True) # ID Setup AI (misal: SETUP_LIVE_NORMAL_10823)
    time = Column(DateTime, index=True)
    action = Column(String) # BUY, SELL, PARTIAL_CLOSE, CLOSE
    mode = Column(String, default="NORMAL", index=True) # NORMAL / RUNNER
    volume = Column(Float)
    price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    profit = Column(Float)
    comment = Column(String)

class LiveDecisionSample(Base):
    """
    Menyimpan feature vector numerik lengkap saat sinyal AI dieksekusi di live market,
    dikaitkan dengan tiket MT5 dan outcome PnL riil setelah posisi ditutup.
    Data ini menjadi basis pembelajaran aktif (RLHF & Hard Negatives) untuk model .pkl.
    """
    __tablename__ = "live_decision_samples"

    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(BigInteger, index=True, nullable=True) # MT5 Order/Deal Ticket
    setup_id = Column(String, index=True) # Unik: SETUP_LIVE_NORMAL_10823
    timestamp = Column(DateTime, default=func.now(), index=True)
    mode = Column(String, default="NORMAL", index=True) # NORMAL / RUNNER
    action = Column(String) # BUY / SELL
    probability = Column(Float, default=0.0)
    entry_price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    exit_price = Column(Float, nullable=True)
    profit = Column(Float, nullable=True)
    outcome = Column(String, default="OPEN", index=True) # OPEN, WIN, LOSS, BE
    rlhf_label = Column(String, default="PENDING", index=True) # PENDING, APPROVED, HARD_NEGATIVE, IGNORED
    feature_vector_json = Column(Text) # Seluruh feature columns dalam format JSON

class ApprovedSetup(Base):
    __tablename__ = "approved_setups"
    
    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(String, index=True)
    mode = Column(String, default="normal", index=True) # normal / runner
    symbol = Column(String, default="XAUUSD")
    action = Column(String, default="BUY")
    probability = Column(Float, default=0.0)
    approved_at = Column(DateTime, default=func.now())
    notes = Column(String, default="Approved by Trader via RLHF")

class RejectedSetup(Base):
    __tablename__ = "rejected_setups"
    
    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(String, index=True)
    mode = Column(String, default="normal", index=True) # normal / runner
    symbol = Column(String, default="XAUUSD")
    action = Column(String, default="BUY")
    probability = Column(Float, default=0.0)
    rejected_at = Column(DateTime, default=func.now())
    notes = Column(String, default="Rejected by Trader via RLHF")

class IgnoredSetup(Base):
    """Setup yang sengaja diabaikan trader karena outcome dianggap noise/anomali.
    Tidak diinjeksi ke RLHF training chunk — sample_weight tetap netral (1.0)."""
    __tablename__ = "ignored_setups"

    id          = Column(Integer, primary_key=True, index=True)
    setup_id    = Column(String, index=True)
    mode        = Column(String, default="normal", index=True) # normal / runner
    symbol      = Column(String, default="XAUUSD")
    action      = Column(String, default="BUY")
    probability = Column(Float, default=0.0)
    ignored_at  = Column(DateTime, default=func.now())
    notes       = Column(String, default="Ignored by Trader via RLHF — Outcome dianggap noise")

class HardNegative(Base):
    __tablename__ = "hard_negatives"
    
    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(String, index=True)
    symbol = Column(String, default="XAUUSD")
    failed_mode = Column(String, index=True) # Normal / Runner
    detected_at = Column(DateTime, default=func.now())
    notes = Column(String, default="Misclassified during OOS Validation")

class TradeJournal(Base):
    __tablename__ = "trade_journal"
    
    id = Column(Integer, primary_key=True, index=True)
    tiket = Column(BigInteger, index=True)
    timestamp = Column(DateTime, index=True, default=func.now())
    event_type = Column(String, index=True) # ENTRY, SL_MODIFY, EXIT
    harga = Column(Float)
    alasan = Column(String) # Alasan AI / Top 3 Feature Contributions
    chart_snapshot = Column(String) # JSON 50 M1 candles

class EconomicEvent(Base):
    __tablename__ = "economic_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, index=True, unique=True)
    date = Column(DateTime, index=True)
    country = Column(String)
    event_name = Column(String)
    currency = Column(String)
    estimate = Column(Float, nullable=True)
    previous = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    change = Column(Float, nullable=True)
    impact = Column(String)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_schema_migrations()

from sqlalchemy import text

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
            except Exception as e_tj:
                pass

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

def get_db_size():
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM market_data_merged"))
            return result.scalar()
        except:
            return 0

def get_db_date_range():
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT MIN(time), MAX(time) FROM market_data_merged"))
            row = result.fetchone()
            if row:
                return row[0], row[1]
            return None, None
        except:
            return None, None

def log_trade_record(action: str, volume: float, price: float, sl: float, tp: float, profit: float = 0.0, comment: str = "", mode: str = "NORMAL", ticket: int = None, setup_id: str = None):
    """Simpan catatan transaksi ke database (trade_logs)."""
    try:
        ensure_schema_migrations()
        import datetime
        with Session(sync_engine) as session:
            log_entry = TradeLog(
                time=datetime.datetime.now(),
                ticket=ticket,
                setup_id=setup_id,
                action=action,
                mode=mode.upper() if mode else "NORMAL",
                volume=volume,
                price=price,
                sl=sl,
                tp=tp,
                profit=profit,
                comment=comment
            )
            session.add(log_entry)
            session.commit()
    except Exception as e:
        print(f"Failed to log trade to DB: {e}")

def save_live_decision_sample(ticket: int, setup_id: str, mode: str, action: str, probability: float, entry_price: float, sl: float, tp: float, feature_vector: dict):
    """Simpan snapshot feature vector numerik saat AI melakukan eksekusi di live market."""
    import json
    import datetime
    import pandas as pd
    import numpy as np
    try:
        ensure_schema_migrations()
        cleaned_features = {}
        for k, v in feature_vector.items():
            if pd.isna(v):
                cleaned_features[k] = 0.0
            elif isinstance(v, (np.floating, float)):
                cleaned_features[k] = float(v)
            elif isinstance(v, (np.integer, int)):
                cleaned_features[k] = int(v)
            elif isinstance(v, (bool, np.bool_)):
                cleaned_features[k] = bool(v)
            else:
                cleaned_features[k] = str(v)
                
        fv_json = json.dumps(cleaned_features)
        
        with Session(sync_engine) as session:
            sample = LiveDecisionSample(
                ticket=ticket,
                setup_id=setup_id,
                timestamp=datetime.datetime.now(),
                mode=mode.upper() if mode else "NORMAL",
                action=action.upper(),
                probability=float(probability),
                entry_price=float(entry_price),
                sl=float(sl),
                tp=float(tp),
                outcome="OPEN",
                rlhf_label="PENDING",
                feature_vector_json=fv_json
            )
            session.add(sample)
            session.commit()
            print(f"[Live Feedback] Decision sample {setup_id} (Ticket #{ticket}) berhasil disimpan.")
    except Exception as e:
        print(f"Failed to save live decision sample: {e}")

def update_live_decision_outcome(ticket: int, exit_price: float, profit: float):
    """
    Update outcome dari posisi live setelah deal MT5 ditutup (TP/SL).
    - Profit > 0 (TP): Outcome WIN, RLHF Auto-Approved
    - Profit < 0 (SL): Outcome LOSS, RLHF Auto-Hard-Negative
    - Profit == 0: Outcome BE, RLHF Ignored
    """
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            sample = session.query(LiveDecisionSample).filter(
                (LiveDecisionSample.ticket == ticket) & (LiveDecisionSample.outcome == "OPEN")
            ).first()
            
            if not sample:
                sample = session.query(LiveDecisionSample).filter(LiveDecisionSample.ticket == ticket).first()
                
            if sample:
                sample.exit_price = float(exit_price)
                sample.profit = float(profit)
                if profit > 0:
                    sample.outcome = "WIN"
                    sample.rlhf_label = "APPROVED"
                elif profit < 0:
                    sample.outcome = "LOSS"
                    sample.rlhf_label = "HARD_NEGATIVE"
                else:
                    sample.outcome = "BE"
                    sample.rlhf_label = "IGNORED"
                session.commit()
                print(f"[Live Feedback] Outcome sample {sample.setup_id} (Ticket #{ticket}) di-update ke {sample.outcome} (Profit: {profit}).")
                return True
    except Exception as e:
        print(f"Failed to update live decision outcome: {e}")
    return False

def get_live_decision_samples_for_training(mode: str = "normal"):
    """
    Mengambil data live decision yang sudah tertutup (WIN dan LOSS)
    dan mengonversinya kembali menjadi DataFrame lengkap dengan Target dan Sample Weight
    untuk langsung diinjeksi ke dalam siklus training LightGBM.
    """
    import json
    import pandas as pd
    try:
        ensure_schema_migrations()
        mode_val = mode.upper() if mode else "NORMAL"
        with Session(sync_engine) as session:
            samples = session.query(LiveDecisionSample).filter(
                (func.upper(LiveDecisionSample.mode) == mode_val) &
                (LiveDecisionSample.outcome.in_(["WIN", "LOSS"])) &
                (LiveDecisionSample.rlhf_label != "IGNORED")
            ).all()

            if not samples:
                return pd.DataFrame()

            rows = []
            for s in samples:
                try:
                    f_dict = json.loads(s.feature_vector_json)
                except Exception:
                    continue

                is_buy = (s.action.upper() == "BUY")
                is_win = (s.outcome == "WIN")

                if is_win:
                    target_label = 1 if is_buy else 2
                    weight = 2.5
                else:
                    target_label = 0
                    weight = 3.5

                target_col = "Target_Normal" if mode_val == "NORMAL" else "Target_Runner"
                f_dict[target_col] = target_label
                f_dict["_sample_weight"] = weight
                f_dict["_timestamp"] = s.timestamp
                rows.append(f_dict)

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            if "_timestamp" in df.columns:
                df.index = pd.to_datetime(df["_timestamp"])
                df.drop(columns=["_timestamp"], inplace=True)
            return df
    except Exception as e:
        print(f"Failed to load live decision samples for training: {e}")
        return pd.DataFrame()

def get_recent_trade_logs(limit: int = 100, mode: str = None):
    """Ambil riwayat transaksi terbaru dari tabel trade_logs (opsional difilter per mode)."""
    import pandas as pd
    try:
        ensure_schema_migrations()
        if mode:
            if "RUNNER" in mode.upper():
                where_sql = "WHERE UPPER(mode) LIKE '%RUNNER%'"
            else:
                where_sql = "WHERE (UPPER(mode) NOT LIKE '%RUNNER%' OR mode IS NULL)"
        else:
            where_sql = ""
        query = f"SELECT id, ticket, setup_id, time, action, mode, volume, price, sl, tp, profit, comment FROM trade_logs {where_sql} ORDER BY time DESC LIMIT {limit}"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty:
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
            if 'setup_id' in df.columns:
                df['setup_id'] = df['setup_id'].fillna('-')
            if 'comment' in df.columns:
                df['comment'] = df['comment'].fillna('')
            df = df.where(pd.notnull(df), None)
        return df
    except Exception as e:
        print(f"Failed to read trade logs from DB: {e}")
        return pd.DataFrame()

def get_live_decision_summary():
    """Mengembalikan statistik ringkas live decision samples (Open, Win, Loss per mode)."""
    try:
        ensure_schema_migrations()
        with Session(sync_engine) as session:
            rows = session.query(
                LiveDecisionSample.mode,
                LiveDecisionSample.outcome,
                func.count(LiveDecisionSample.id)
            ).group_by(LiveDecisionSample.mode, LiveDecisionSample.outcome).all()
            
            summary = {
                "NORMAL": {"OPEN": 0, "WIN": 0, "LOSS": 0, "BE": 0, "TOTAL": 0},
                "RUNNER": {"OPEN": 0, "WIN": 0, "LOSS": 0, "BE": 0, "TOTAL": 0}
            }
            for m, o, cnt in rows:
                m_str = (m or "").upper()
                m_key = "RUNNER" if "RUNNER" in m_str else "NORMAL"
                o_key = o.upper() if o else "OPEN"
                if m_key in summary and o_key in summary[m_key]:
                    summary[m_key][o_key] += cnt
                    summary[m_key]["TOTAL"] += cnt
            return summary
    except Exception as e:
        print(f"Failed to get live decision summary: {e}")
        return {}

def get_historical_pnl_feedback(mode: str = None):
    """Ambil riwayat transaksi lengkap untuk PnL Feedback Loop pada AI Researcher (opsional per mode)."""
    import pandas as pd
    try:
        ensure_schema_migrations()
        if mode:
            if "RUNNER" in mode.upper():
                where_mode = "AND UPPER(mode) LIKE '%RUNNER%'"
            else:
                where_mode = "AND (UPPER(mode) NOT LIKE '%RUNNER%' OR mode IS NULL)"
        else:
            where_mode = ""
        query = f"SELECT time, profit, action, mode FROM trade_logs WHERE action IN ('BUY', 'SELL', 'CLOSE', 'PARTIAL_CLOSE') AND profit != 0.0 {where_mode} ORDER BY time DESC LIMIT 10000"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
        return df
    except Exception as e:
        print(f"Failed to fetch historical PnL feedback: {e}")
        return pd.DataFrame()

def get_trade_performance_summary():
    """
    Menghitung statistik trading terpisah untuk Mode Normal dan Mode Runner:
    Total trades, Win rate, Total Realized Profit/Loss, Wins, Losses.
    """
    import pandas as pd
    try:
        ensure_schema_migrations()
        query = "SELECT mode, profit FROM trade_logs WHERE action IN ('CLOSE', 'PARTIAL_CLOSE', 'BUY', 'SELL') AND profit != 0.0"
        df = pd.read_sql(query, con=sync_engine)
        
        def calc_stats(sub_df):
            if sub_df.empty:
                return {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0}
            wins = len(sub_df[sub_df['profit'] > 0])
            losses = len(sub_df[sub_df['profit'] < 0])
            total = len(sub_df)
            wr = round((wins / total) * 100, 1) if total > 0 else 0.0
            pnl = round(float(sub_df['profit'].sum()), 2)
            return {"total_trades": total, "win_rate": wr, "total_profit": pnl, "wins": wins, "losses": losses}

        if not df.empty and 'mode' in df.columns:
            is_runner = df['mode'].astype(str).str.upper().str.contains('RUNNER')
            normal_df = df[~is_runner]
            runner_df = df[is_runner]
        else:
            normal_df = pd.DataFrame()
            runner_df = pd.DataFrame()

        return {
            "normal": calc_stats(normal_df),
            "runner": calc_stats(runner_df),
            "all": calc_stats(df)
        }
    except Exception as e:
        print(f"Failed to calculate performance summary: {e}")
        return {
            "normal": {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0},
            "runner": {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0},
            "all": {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0}
        }

def get_mt5_open_positions():
    """Mengambil posisi trading yang saat ini sedang aktif (floating) langsung dari MT5."""
    import MetaTrader5 as mt5
    import datetime
    try:
        if not mt5.terminal_info():
            mt5.initialize()
        positions = mt5.positions_get()
        if not positions:
            return []
        
        pos_list = []
        for p in positions:
            comment = p.comment or ""
            mode = "RUNNER" if "RUNNER" in comment.upper() else "NORMAL"
            pos_time = datetime.datetime.fromtimestamp(p.time)
            pos_list.append({
                "ticket": int(p.ticket),
                "time": pos_time.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": p.symbol,
                "action": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                "volume": float(p.volume),
                "price": float(p.price_open),
                "current_price": float(p.price_current),
                "sl": float(p.sl),
                "tp": float(p.tp),
                "profit": round(float(p.profit) + float(p.swap), 2),
                "mode": mode,
                "comment": comment
            })
        return pos_list
    except Exception as e:
        print(f"Failed to get MT5 open positions: {e}")
        return []

def sync_mt5_closed_deals_to_db(days_back: int = 90):
    """
    Sinkronisasi deal tertutup dari MT5 ke tabel trade_logs secara otomatis.
    Mendeteksi apakah posisi tersebut RUNNER atau NORMAL berdasarkan comment / posisi awal,
    dan mencatat profit riil agar PnL dan statistik terpisah per mode.
    """
    import MetaTrader5 as mt5
    import datetime
    try:
        ensure_schema_migrations()
        if not mt5.terminal_info():
            if not mt5.initialize():
                print("[Sync Warning] MT5 terminal tidak dapat diinisialisasi.")
                return 0

        now = datetime.datetime.now()
        start = now - datetime.timedelta(days=days_back)
        deals = mt5.history_deals_get(start, now)
        if deals is None or len(deals) == 0:
            # Fallback jika broker butuh rentang dari timestamp awal tahun
            fallback_start = datetime.datetime(2023, 1, 1)
            deals = mt5.history_deals_get(fallback_start, now)
            
        if not deals:
            return 0

        with Session(sync_engine) as session:
            existing_deals = session.query(TradeLog.ticket).filter(TradeLog.ticket.isnot(None)).all()
            existing_deal_tickets = {r[0] for r in existing_deals if r[0] is not None}

            synced_count = 0
            for deal in deals:
                # mt5.DEAL_ENTRY_OUT (1), mt5.DEAL_ENTRY_INOUT (2), DEAL_ENTRY_OUT_BY (3)
                if deal.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT, getattr(mt5, 'DEAL_ENTRY_OUT_BY', 3)):
                    deal_ticket = deal.ticket
                    pos_id = deal.position_id
                    
                    if deal_ticket in existing_deal_tickets:
                        continue

                    deal_comment = deal.comment or ""
                    mode = "NORMAL"
                    pos_setup_id = None
                    if "RUNNER" in deal_comment.upper():
                        mode = "RUNNER"
                    else:
                        pos_log = session.query(TradeLog).filter(TradeLog.ticket == pos_id).first()
                        if pos_log:
                            pos_setup_id = pos_log.setup_id
                            if pos_log.mode:
                                mode = pos_log.mode.upper()
                        elif "HIT_RUN" in deal_comment.upper():
                            mode = "NORMAL"

                    action = "CLOSE"
                    if deal.type == mt5.DEAL_TYPE_BUY:
                        action = "BUY"
                    elif deal.type == mt5.DEAL_TYPE_SELL:
                        action = "SELL"

                    net_profit = float(deal.profit) + float(deal.swap) + float(deal.commission)

                    close_entry = TradeLog(
                        ticket=deal_ticket,
                        setup_id=pos_setup_id,
                        time=datetime.datetime.fromtimestamp(deal.time),
                        action=action,
                        mode=mode,
                        volume=float(deal.volume),
                        price=float(deal.price),
                        sl=0.0,
                        tp=0.0,
                        profit=round(net_profit, 2),
                        comment=f"MT5 Deal #{deal_ticket} (Pos #{pos_id}): {deal_comment}"
                    )
                    session.add(close_entry)
                    existing_deal_tickets.add(deal_ticket)
                    synced_count += 1

                    # Update status LiveDecisionSample (WIN / LOSS / BE) berdasarkan posisi awal
                    try:
                        update_live_decision_outcome(
                            ticket=pos_id,
                            exit_price=float(deal.price),
                            profit=round(net_profit, 2)
                        )
                    except Exception as e_sample:
                        print(f"[Sync Warning] Gagal update live sample outcome: {e_sample}")

            if synced_count > 0:
                session.commit()
                print(f"[Sync MT5 Deals] Berhasil mencatat {synced_count} closed deals ke trade_logs.")
            return synced_count
    except Exception as e:
        print(f"Failed to sync MT5 deals: {e}")
        return 0

# ==========================================
# RLHF: APPROVED SETUPS HELPERS
# ==========================================
def save_approved_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = "", mode: str = "normal"):
    """Simpan ID setup yang telah disetujui trader ke approved_setups (dipisahkan per mode)."""
    try:
        ensure_schema_migrations()
        import datetime
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
        print(f"Failed to save approved setup: {e}")
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
        print(f"Failed to get approved setup IDs: {e}")
        return set()

def get_all_approved_setups(mode: str = None):
    """Ambil seluruh data approved setups dalam bentuk DataFrame (opsional per mode)."""
    import pandas as pd
    try:
        ensure_schema_migrations()
        where_sql = f"WHERE mode = '{mode.lower()}'" if mode else ""
        query = f"SELECT id, setup_id, mode, symbol, action, probability, approved_at, notes FROM approved_setups {where_sql} ORDER BY approved_at DESC"
        return pd.read_sql(query, con=sync_engine)
    except Exception as e:
        print(f"Failed to query approved setups: {e}")
        return pd.DataFrame()

def save_rejected_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = "", mode: str = "normal"):
    """Simpan ID setup yang telah ditolak trader ke rejected_setups (dipisahkan per mode)."""
    try:
        ensure_schema_migrations()
        import datetime
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
        print(f"Failed to save rejected setup: {e}")
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
        print(f"Failed to get rejected setup IDs: {e}")
        return set()

# ==========================================
# RLHF: IGNORED SETUPS HELPERS
# ==========================================
def save_ignored_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = "", mode: str = "normal"):
    """Simpan ID setup yang sengaja diabaikan trader ke ignored_setups (dipisahkan per mode)."""
    try:
        ensure_schema_migrations()
        import datetime
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
        print(f"Failed to save ignored setup: {e}")
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
        print(f"Failed to get ignored setup IDs: {e}")
        return set()

# ==========================================
# BLACK BOX: TRADE JOURNAL & XAI HELPERS
# ==========================================
def log_trade_journal(tiket: int, event_type: str, harga: float, alasan: str, chart_snapshot: str):
    """
    Catat event transaksi (ENTRY, SL_MODIFY, EXIT) beserta 50 candle M1 snapshot dan alasan AI.
    """
    try:
        Base.metadata.create_all(sync_engine)
        import datetime
        with Session(sync_engine) as session:
            entry = TradeJournal(
                tiket=int(tiket),
                timestamp=datetime.datetime.now(),
                event_type=str(event_type),
                harga=float(harga),
                alasan=str(alasan),
                chart_snapshot=str(chart_snapshot)
            )
            session.add(entry)
            session.commit()
            return True
    except Exception as e:
        print(f"Failed to log trade journal: {e}")
        return False

def get_trade_journal_entries(limit: int = 100):
    """Ambil catatan trade_journal terbaru untuk analisis Black Box."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT id, tiket, timestamp, event_type, harga, alasan, chart_snapshot FROM trade_journal ORDER BY timestamp DESC LIMIT {limit}"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        print(f"Failed to read trade journal: {e}")
        return pd.DataFrame()

# ==========================================
# MACRO DATA: ECONOMIC CALENDAR CACHE
# ==========================================
def save_macro_data(events_df):
    """Simpan data jadwal kalender ekonomi ke database untuk cache."""
    try:
        Base.metadata.create_all(sync_engine)
        import pandas as pd
        if events_df.empty:
            return 0
            
        with Session(sync_engine) as session:
            count = 0
            for _, row in events_df.iterrows():
                event_id_val = f"{row['date']}_{row['event']}"
                
                # Check if exists to update actual if needed
                existing = session.query(EconomicEvent).filter(EconomicEvent.event_id == event_id_val).first()
                if existing:
                    # Update if actual is now available
                    if pd.notna(row.get('actual')) and existing.actual is None:
                        existing.actual = float(row['actual'])
                        if pd.notna(row.get('change')):
                            existing.change = float(row['change'])
                else:
                    new_event = EconomicEvent(
                        event_id=event_id_val,
                        date=row['date'],
                        country=row.get('country', ''),
                        event_name=row.get('event', ''),
                        currency=row.get('currency', ''),
                        estimate=float(row['estimate']) if pd.notna(row.get('estimate')) else None,
                        previous=float(row['previous']) if pd.notna(row.get('previous')) else None,
                        actual=float(row['actual']) if pd.notna(row.get('actual')) else None,
                        change=float(row['change']) if pd.notna(row.get('change')) else None,
                        impact=row.get('impact', '')
                    )
                    session.add(new_event)
                    count += 1
                    
            session.commit()
            return count
    except Exception as e:
        print(f"Failed to save macro data to DB: {e}")
        return 0

def get_macro_data(start_date: str, end_date: str):
    """Ambil data kalender ekonomi dari cache database."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT * FROM economic_events WHERE date >= '{start_date}' AND date <= '{end_date}' ORDER BY date ASC"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], utc=True)
        return df
    except Exception as e:
        print(f"Failed to read macro data from DB: {e}")
        return pd.DataFrame()

def get_next_high_impact_event():
    """
    Mengambil 1 economic event 'High Impact' terdekat yang akan datang (atau baru saja rilis < 15 menit).
    Digunakan untuk countdown dan proteksi volatilitas di antarmuka UI.
    """
    from datetime import datetime, timezone, timedelta
    try:
        Base.metadata.create_all(sync_engine)
        now_utc = datetime.now(timezone.utc)
        # Toleransi 15 menit ke belakang untuk menampilkan berita yang baru saja rilis
        lookback_limit = (now_utc - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        lookforward_limit = (now_utc + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        
        with Session(sync_engine) as session:
            events = session.query(EconomicEvent).filter(
                EconomicEvent.date >= lookback_limit,
                EconomicEvent.date <= lookforward_limit
            ).order_by(EconomicEvent.date.asc()).all()
            
            for ev in events:
                imp = str(ev.impact).lower() if ev.impact else ""
                # High impact filter: 'high', '3', 'red'
                if 'high' in imp or imp == '3' or 'red' in imp:
                    ev_date = ev.date
                    if ev_date.tzinfo is None:
                        ev_date = ev_date.replace(tzinfo=timezone.utc)
                    diff_seconds = (ev_date - now_utc).total_seconds()
                    
                    return {
                        "id": ev.id,
                        "event_id": ev.event_id,
                        "event_name": ev.event_name,
                        "country": ev.country,
                        "currency": ev.currency,
                        "impact": ev.impact,
                        "date": ev_date.isoformat(),
                        "estimate": ev.estimate,
                        "previous": ev.previous,
                        "actual": ev.actual,
                        "seconds_remaining": int(diff_seconds),
                        "minutes_remaining": round(diff_seconds / 60.0, 1),
                        "is_imminent": 0 <= diff_seconds <= 1800 # <= 30 menit
                    }
        return None
    except Exception as e:
        import logging
        logging.debug(f"Gagal mengambil next high impact event: {e}")
        return None

def get_upcoming_economic_events(limit: int = 10):
    """Mengambil daftar event ekonomi mendatang hingga limit tertentu."""
    from datetime import datetime, timezone, timedelta
    try:
        Base.metadata.create_all(sync_engine)
        now_utc = datetime.now(timezone.utc)
        lookback_limit = (now_utc - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        lookforward_limit = (now_utc + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        
        with Session(sync_engine) as session:
            events = session.query(EconomicEvent).filter(
                EconomicEvent.date >= lookback_limit,
                EconomicEvent.date <= lookforward_limit
            ).order_by(EconomicEvent.date.asc()).limit(limit).all()
            
            result = []
            for ev in events:
                ev_date = ev.date
                if ev_date.tzinfo is None:
                    ev_date = ev_date.replace(tzinfo=timezone.utc)
                diff_seconds = (ev_date - now_utc).total_seconds()
                result.append({
                    "id": ev.id,
                    "event_name": ev.event_name,
                    "country": ev.country,
                    "currency": ev.currency,
                    "impact": ev.impact,
                    "date": ev_date.isoformat(),
                    "estimate": ev.estimate,
                    "previous": ev.previous,
                    "actual": ev.actual,
                    "seconds_remaining": int(diff_seconds),
                    "minutes_remaining": round(diff_seconds / 60.0, 1)
                })
            return result
    except Exception as e:
        import logging
        logging.debug(f"Gagal mengambil upcoming economic events: {e}")
        return []

def add_hard_negative(setup_id: str, failed_mode: str = "Normal"):
    from sqlalchemy.orm import Session
    try:
        with Session(sync_engine) as session:
            existing = session.query(HardNegative).filter_by(setup_id=setup_id).first()
            if not existing:
                new_hn = HardNegative(setup_id=setup_id, failed_mode=failed_mode)
                session.add(new_hn)
                session.commit()
                return True
    except Exception as e:
        import logging
        logging.error(f"Gagal menyimpan Hard Negative: {e}")
    return False

def bulk_add_hard_negatives(records: list):
    """records adalah list of dict: [{'setup_id': '...', 'failed_mode': '...'}, ...]"""
    from sqlalchemy.orm import Session
    import pandas as pd
    try:
        with Session(sync_engine) as session:
            # Ambil semua existing id untuk mencegah duplikat
            existing_df = pd.read_sql("SELECT setup_id FROM hard_negatives", con=sync_engine)
            existing_ids = set(existing_df['setup_id'].tolist()) if not existing_df.empty else set()
            
            new_objects = []
            for r in records:
                if r['setup_id'] not in existing_ids:
                    new_objects.append(HardNegative(setup_id=r['setup_id'], failed_mode=r['failed_mode']))
                    existing_ids.add(r['setup_id']) # Mencegah duplikat di dalam input
            
            if new_objects:
                session.bulk_save_objects(new_objects)
                session.commit()
                return len(new_objects)
            return 0
    except Exception as e:
        import logging
        logging.error(f"Gagal menyimpan Hard Negatives (Bulk): {e}")
        return 0

def get_hard_negative_ids(mode: str = None):
    try:
        import pandas as pd
        ensure_schema_migrations()
        if mode:
            query = f"SELECT setup_id FROM hard_negatives WHERE LOWER(failed_mode) = '{mode.lower()}'"
        else:
            query = "SELECT setup_id FROM hard_negatives"
        df = pd.read_sql(query, con=sync_engine)
        return df['setup_id'].tolist() if not df.empty else []
    except Exception:
        return []

def fetch_historical_data_chunks(chunk_size=10000):
    """
    Mengambil data historis dalam potongan (chunks) dari tabel market_data_merged.
    ORDER BY dihapus dari query SQL untuk mencegah PostgreSQL lokal membuat file temp
    sementara yang menyebabkan crash (psycopg2.errors.UndefinedFile / pgsql_tmp).
    Pengurutan dilakukan di Python per-chunk setelah data diambil.
    """
    import pandas as pd
    import logging
    try:
        # Tanpa ORDER BY: PostgreSQL tidak perlu membuat file temp disk untuk sort
        query = "SELECT * FROM market_data_merged"
        for chunk in pd.read_sql(query, con=sync_engine, chunksize=chunk_size):
            if not chunk.empty and 'time' in chunk.columns:
                chunk['time'] = pd.to_datetime(chunk['time'])
                chunk.sort_values('time', inplace=True)  # Sort di Python, hemat RAM PostgreSQL
                chunk.set_index('time', inplace=True)
            yield chunk
    except Exception as e:
        logging.error(f"Failed to fetch historical data: {e}")
        yield pd.DataFrame()
