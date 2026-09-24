import datetime
import json
import re
import logging
import pandas as pd
import numpy as np
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from ..connection import sync_engine, Base
from ..models.trade import TradeLog, LiveDecisionSample, TradeJournal
from ..migrations import ensure_schema_migrations

def log_trade_record(action: str, volume: float, price: float, sl: float, tp: float, profit: float = 0.0, comment: str = "", mode: str = "NORMAL", ticket: int = None, setup_id: str = None):
    """Simpan catatan transaksi ke database (trade_logs)."""
    try:
        ensure_schema_migrations()
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
        logging.error(f"Failed to log trade to DB: {e}")

def save_live_decision_sample(ticket: int, setup_id: str, mode: str, action: str, probability: float, entry_price: float, sl: float, tp: float, feature_vector: dict):
    """Simpan snapshot feature vector numerik saat AI melakukan eksekusi di live market."""
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
            logging.info(f"[Live Feedback] Decision sample {setup_id} (Ticket #{ticket}) berhasil disimpan.")
    except Exception as e:
        logging.error(f"Failed to save live decision sample: {e}")

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
                logging.info(f"[Live Feedback] Outcome sample {sample.setup_id} (Ticket #{ticket}) di-update ke {sample.outcome} (Profit: {profit}).")
                return True
    except Exception as e:
        logging.error(f"Failed to update live decision outcome: {e}")
    return False

def get_live_decision_samples_for_training(mode: str = "normal"):
    """
    Mengambil data live decision yang sudah tertutup (WIN dan LOSS)
    dan mengonversinya kembali menjadi DataFrame lengkap dengan Target dan Sample Weight.
    """
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
        logging.error(f"Failed to load live decision samples for training: {e}")
        return pd.DataFrame()

def get_recent_trade_logs(limit: int = 100, mode: str = None, only_closed: bool = True):
    """Ambil riwayat transaksi terbaru dari tabel trade_logs (opsional difilter per mode)."""
    try:
        ensure_schema_migrations()
        where_clauses = []
        if only_closed:
            where_clauses.append("profit != 0.0")
        if mode:
            if "RUNNER" in mode.upper():
                where_clauses.append("UPPER(mode) LIKE '%RUNNER%'")
            else:
                where_clauses.append("(UPPER(mode) NOT LIKE '%RUNNER%' OR mode IS NULL)")
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT id, ticket, setup_id, time, action, mode, volume, price, sl, tp, profit, comment FROM trade_logs {where_sql} ORDER BY time DESC LIMIT {limit}"
        with sync_engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
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
        logging.error(f"Failed to read trade logs from DB: {e}")
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
        logging.error(f"Failed to get live decision summary: {e}")
        return {}

def get_historical_pnl_feedback(mode: str = None):
    """Ambil riwayat transaksi lengkap untuk PnL Feedback Loop pada AI Researcher."""
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
        with sync_engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
        if not df.empty and 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
        return df
    except Exception as e:
        logging.error(f"Failed to fetch historical PnL feedback: {e}")
        return pd.DataFrame()

def get_trade_performance_summary():
    """
    Menghitung statistik trading terpisah untuk Mode Normal dan Mode Runner:
    Total trades, Win rate, Total Realized Profit/Loss, Wins, Losses.
    """
    try:
        ensure_schema_migrations()
        query = "SELECT mode, profit FROM trade_logs WHERE action IN ('CLOSE', 'PARTIAL_CLOSE', 'BUY', 'SELL') AND profit != 0.0"
        with sync_engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
        
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
        logging.error(f"Failed to calculate performance summary: {e}")
        return {
            "normal": {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0},
            "runner": {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0},
            "all": {"total_trades": 0, "win_rate": 0.0, "total_profit": 0.0, "wins": 0, "losses": 0}
        }

def get_mt5_open_positions():
    """Mengambil posisi trading yang saat ini sedang aktif (floating) langsung dari MT5."""
    import MetaTrader5 as mt5
    try:
        if not mt5.terminal_info():
            mt5.initialize()
        positions = mt5.positions_get()
        if not positions:
            return []
        
        pos_list = []
        for p in positions:
            comment = p.comment or ""
            magic = getattr(p, 'magic', 0)
            if magic == 234002 or "RUNNER" in comment.upper():
                mode = "RUNNER"
            elif magic == 234001 or "HIT_RUN" in comment.upper():
                mode = "NORMAL"
            else:
                mode = "NORMAL"
                try:
                    with Session(sync_engine) as sess:
                        t_rec = sess.query(TradeLog).filter(TradeLog.ticket == int(p.ticket)).first()
                        if t_rec and t_rec.mode:
                            mode = t_rec.mode.upper()
                except Exception:
                    pass

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
        logging.error(f"Failed to get MT5 open positions: {e}")
        return []

def sync_mt5_closed_deals_to_db(days_back: int = 90):
    """
    Sinkronisasi deal tertutup dari MT5 ke tabel trade_logs secara otomatis.
    """
    import MetaTrader5 as mt5
    try:
        ensure_schema_migrations()
        if not mt5.terminal_info():
            if not mt5.initialize():
                logging.warning("[Sync Warning] MT5 terminal tidak dapat diinisialisasi.")
                return 0

        now = datetime.datetime.now()
        start = now - datetime.timedelta(days=days_back)
        deals = mt5.history_deals_get(start, now)
        if deals is None or len(deals) == 0:
            fallback_start = datetime.datetime(2023, 1, 1)
            deals = mt5.history_deals_get(fallback_start, now)
            
        if not deals:
            return 0

        with Session(sync_engine) as session:
            existing_deal_tickets = set()
            for (c,) in session.query(TradeLog.comment).filter(TradeLog.comment.like('%MT5 Deal #%')).all():
                if c:
                    m = re.search(r'MT5 Deal #(\d+)', c)
                    if m:
                        existing_deal_tickets.add(int(m.group(1)))
            for (t,) in session.query(TradeLog.ticket).filter(TradeLog.ticket.isnot(None)).all():
                if t:
                    existing_deal_tickets.add(int(t))

            synced_count = 0
            for deal in deals:
                if deal.entry in (mt5.DEAL_ENTRY_OUT, mt5.DEAL_ENTRY_INOUT, getattr(mt5, 'DEAL_ENTRY_OUT_BY', 3)):
                    deal_ticket = int(deal.ticket)
                    pos_id = int(deal.position_id)
                    deal_magic = getattr(deal, 'magic', 0)
                    
                    if deal_ticket in existing_deal_tickets:
                        continue

                    deal_comment = deal.comment or ""
                    mode = "NORMAL"
                    pos_setup_id = None
                    action = "BUY"

                    pos_log = session.query(TradeLog).filter(TradeLog.ticket == pos_id).first()
                    if pos_log:
                        pos_setup_id = pos_log.setup_id
                        if pos_log.mode:
                            mode = pos_log.mode.upper()
                        if pos_log.action and pos_log.action in ("BUY", "SELL"):
                            action = pos_log.action
                    else:
                        if deal.type == mt5.DEAL_TYPE_SELL:
                            action = "BUY"
                        elif deal.type == mt5.DEAL_TYPE_BUY:
                            action = "SELL"
                        else:
                            action = "BUY"

                    if deal_magic == 234002 or "RUNNER" in deal_comment.upper():
                        mode = "RUNNER"
                    elif deal_magic == 234001 or "HIT_RUN" in deal_comment.upper():
                        mode = "NORMAL"

                    net_profit = float(deal.profit) + float(deal.swap) + float(deal.commission)

                    close_entry = TradeLog(
                        ticket=pos_id if pos_id else deal_ticket,
                        setup_id=pos_setup_id or f"SETUP_LIVE_{mode}_{pos_id}",
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

                    try:
                        update_live_decision_outcome(
                            ticket=pos_id,
                            exit_price=float(deal.price),
                            profit=round(net_profit, 2)
                        )
                    except Exception as e_sample:
                        logging.warning(f"[Sync Warning] Gagal update live sample outcome: {e_sample}")

            if synced_count > 0:
                session.commit()
                logging.info(f"[Sync MT5 Deals] Berhasil mencatat {synced_count} closed deals ke trade_logs.")
            return synced_count
    except Exception as e:
        logging.error(f"Failed to sync MT5 deals: {e}")
        return 0

def log_trade_journal(tiket: int, event_type: str, harga: float, alasan: str, chart_snapshot: str):
    """
    Catat event transaksi (ENTRY, SL_MODIFY, EXIT) beserta 50 candle M1 snapshot dan alasan AI.
    """
    try:
        Base.metadata.create_all(sync_engine)
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
        logging.error(f"Failed to log trade journal: {e}")
        return False

def get_trade_journal_entries(limit: int = 100):
    """Ambil catatan trade_journal terbaru untuk analisis Black Box."""
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT id, tiket, timestamp, event_type, harga, alasan, chart_snapshot FROM trade_journal ORDER BY timestamp DESC LIMIT {limit}"
        with sync_engine.connect() as conn:
            df = pd.read_sql(text(query), con=conn)
        if not df.empty and 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        logging.error(f"Failed to read trade journal: {e}")
        return pd.DataFrame()
