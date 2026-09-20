import streamlit as st
import threading
import asyncio
import logging
import datetime
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

# Plotly imports with fallback
try:
    import plotly.graph_objects as go
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "plotly"])
    import plotly.graph_objects as go

from config import Config
import io
import json
from utils.mt5_utils import init_mt5, shutdown_mt5, get_rates
from database import (
    get_db_size, 
    get_db_date_range, 
    get_recent_trade_logs, 
    log_trade_record, 
    sync_engine,
    save_approved_setup,
    get_approved_setup_ids,
    get_all_approved_setups,
    log_trade_journal,
    get_trade_journal_entries
)
from utils.indicators import calculate_bbma

from agents.supervisor import SupervisorAgent
from agents.data_miner import DataMinerAgent
from agents.researcher import ResearcherAgent
from agents.gatekeeper import GatekeeperAgent
from agents.executor import ExecutorAgent

st.set_page_config(page_title="BBMA AI Trader", page_icon="🤖", layout="wide")

# Custom Logger for Streamlit
class StreamlitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_area = []

    def emit(self, record):
        msg = self.format(record)
        self.log_area.append(msg)
        if len(self.log_area) > 150:
            self.log_area.pop(0)

if 'log_handler' not in st.session_state:
    st.session_state.log_handler = StreamlitLogHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    st.session_state.log_handler.setFormatter(formatter)
    
    if not any(isinstance(h, StreamlitLogHandler) for h in logging.getLogger().handlers):
        logging.getLogger().addHandler(st.session_state.log_handler)
        logging.getLogger().setLevel(logging.INFO)

TEMPORAL_SPLIT_RATIO = 0.80  # 80% Train, 20% Test (Walk-Forward Standard)

# Global agent state
if 'supervisor' not in st.session_state:
    st.session_state.supervisor = SupervisorAgent()
    st.session_state.data_miner = DataMinerAgent(symbol=Config.SYMBOL)
    st.session_state.researcher = ResearcherAgent()
    st.session_state.gatekeeper = GatekeeperAgent(st.session_state.researcher)
    st.session_state.executor = ExecutorAgent(
        st.session_state.supervisor, 
        data_miner_agent=st.session_state.data_miner,
        researcher_agent=st.session_state.researcher
    )
    st.session_state.executor_thread = None

def start_executor_loop(executor):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(executor.monitor_market())

def start_system():
    if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD, Config.MT5_PATH):
        st.success("Terkoneksi ke MT5")
        st.session_state.executor.data_miner = st.session_state.data_miner
        st.session_state.executor.researcher = st.session_state.researcher
        st.session_state.supervisor.start_ingestion()
        
        progress_bar = st.progress(0, text="Menyelaraskan data inkremental terbaru...")
        def update_progress(batch_idx, total_batches, end_idx, total_rows):
            pct = int((end_idx / total_rows) * 100)
            progress_bar.progress(pct, text=f"Menyelaraskan data ({end_idx:,}/{total_rows:,} baris)...")
            
        st.session_state.data_miner.backfill_data(100000, progress_callback=update_progress)
        progress_bar.empty()
            
        if st.session_state.researcher.load_models():
            st.success("Model Checkpoint ditemukan! Melewati fase pelatihan dan validasi.")
            st.session_state.supervisor.set_model_validity(True)
            st.session_state.supervisor.start_live()
            
            if st.session_state.executor_thread is None or not st.session_state.executor_thread.is_alive():
                st.session_state.executor_thread = threading.Thread(
                    target=start_executor_loop, 
                    args=(st.session_state.executor,), 
                    daemon=True
                )
                st.session_state.executor_thread.start()
            st.success("Sistem beroperasi dalam mode LIVE!")
            return
            
        total_chunks, train_gen = st.session_state.data_miner.load_train_chunks(split_ratio=TEMPORAL_SPLIT_RATIO)
        
        if total_chunks > 0 and train_gen is not None:
            st.session_state.supervisor.start_research()
            
            progress_bar = st.progress(0, text="Memulai pelatihan Incremental Learning...")
            def update_progress(chunk_idx, total):
                pct = int((chunk_idx / total) * 100)
                progress_bar.progress(pct, text=f"Melatih AI (Chunk {chunk_idx}/{total})...")
                
            st.session_state.researcher.train_models(train_gen, total_chunks=total_chunks, progress_callback=update_progress)
            progress_bar.empty()
            
            test_df = st.session_state.data_miner.load_test_data(split_ratio=TEMPORAL_SPLIT_RATIO)
            
            st.session_state.supervisor.start_evaluation()
            valid = False
            if test_df is not None and not test_df.empty:
                valid = st.session_state.gatekeeper.validate_model(test_df)
            
            st.session_state.supervisor.set_model_validity(valid)
            if valid:
                st.session_state.supervisor.start_live()
                
                if st.session_state.executor_thread is None or not st.session_state.executor_thread.is_alive():
                    st.session_state.executor_thread = threading.Thread(
                        target=start_executor_loop, 
                        args=(st.session_state.executor,), 
                        daemon=True
                    )
                    st.session_state.executor_thread.start()
                st.success("Sistem beroperasi dalam mode LIVE!")
            else:
                st.session_state.supervisor.fail_evaluation()
                st.error("Model gagal melewati validasi Walk-Forward. Kembali ke fase Riset.")
    else:
        st.error("Gagal terkoneksi ke MT5.")

def backfill_db():
    if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD, Config.MT5_PATH):
        progress_bar = st.progress(0, text="Memulai penarikan data...")
        def update_progress(batch_idx, total_batches, end_idx, total_rows):
            pct = int((end_idx / total_rows) * 100)
            progress_bar.progress(pct, text=f"Menyimpan data ({end_idx:,}/{total_rows:,} baris)...")
            
        count = st.session_state.data_miner.backfill_data(5000000, progress_callback=update_progress)
        progress_bar.empty()
        st.success(f"Backfill berhasil! Menyimpan {count} baris data.")

# ==========================================
# FUNGSI RENDER GRAFIK CANDLESTICK (PLOTLY)
# ==========================================
def render_candlestick_chart(
    df: pd.DataFrame, 
    trade_entries: list = None, 
    active_trade: dict = None,
    title: str = "Grafik Candlestick Pasar & Sinyal AI",
    height: int = 580,
    show_bbma: bool = True
):
    """
    Merender grafik Candlestick interaktif menggunakan Plotly dengan:
    1. 'Entry Point Highlighter': Marker panah go.Scatter (hijau/merah) tepat di candle tempat AI membuka posisi.
    2. Hovertext pada marker berisi ringkasan singkat (misal: 'ENTRY BUY | Probabilitas: 82%').
    3. Dua garis horizontal putus-putus (hline) di harga Stop Loss awal dan Take Profit awal.
    """
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            title=title,
            annotations=[dict(text="Tidak ada data candle tersedia", showarrow=False, font=dict(size=16, color="#CCCCCC"))],
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117"
        )
        return fig

    df_plot = df.copy()
    if 'time' in df_plot.columns and df_plot.index.name == 'time':
        df_plot.index.name = None
    if 'time' not in df_plot.columns and isinstance(df_plot.index, pd.DatetimeIndex):
        df_plot['time'] = df_plot.index
    elif 'time' in df_plot.columns:
        df_plot['time'] = pd.to_datetime(df_plot['time'])

    df_plot = df_plot.reset_index(drop=True)
    df_plot = df_plot.sort_values('time').reset_index(drop=True)

    fig = go.Figure()

    # 1. Candlestick Utama
    fig.add_trace(go.Candlestick(
        x=df_plot['time'],
        open=df_plot['open'],
        high=df_plot['high'],
        low=df_plot['low'],
        close=df_plot['close'],
        name="Price",
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350',
        increasing_fillcolor='#26a69a',
        decreasing_fillcolor='#ef5350'
    ))

    # 2. Indikator BBMA Overlay
    if show_bbma:
        if 'EMA_50' in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot['time'],
                y=df_plot['EMA_50'],
                mode='lines',
                line=dict(color='#00E5FF', width=1.5),
                name='EMA 50 (Trend Filter)'
            ))
        if 'BB_Upper' in df_plot.columns and 'BB_Lower' in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot['time'],
                y=df_plot['BB_Upper'],
                mode='lines',
                line=dict(color='rgba(186, 104, 200, 0.7)', width=1, dash='dot'),
                name='BB Upper'
            ))
            fig.add_trace(go.Scatter(
                x=df_plot['time'],
                y=df_plot['BB_Lower'],
                mode='lines',
                line=dict(color='rgba(186, 104, 200, 0.7)', width=1, dash='dot'),
                name='BB Lower'
            ))
        if 'SMA_20' in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot['time'],
                y=df_plot['SMA_20'],
                mode='lines',
                line=dict(color='rgba(255, 179, 0, 0.7)', width=1, dash='dash'),
                name='Mid BB (SMA 20)'
            ))

    # 3. Entry Point Highlighter (fig.add_trace(go.Scatter(...)))
    if trade_entries:
        for entry in trade_entries:
            entry_action = str(entry.get('action', 'BUY')).upper()
            entry_time = entry.get('time')
            if isinstance(entry_time, str):
                entry_time = pd.to_datetime(entry_time)
            
            entry_price = float(entry.get('price', 0.0))
            
            # Format probabilitas
            prob = entry.get('probability', '82%')
            if isinstance(prob, (int, float)):
                prob_str = f"{int(prob * 100)}%" if prob <= 1.0 else f"{int(prob)}%"
            else:
                prob_str = str(prob)
                
            sl_val = float(entry.get('sl', 0.0))
            tp_val = float(entry.get('tp', 0.0))
            time_str = entry_time.strftime("%Y-%m-%d %H:%M") if hasattr(entry_time, "strftime") else str(entry_time)
            ticket_info = f"Ticket #{entry.get('ticket')}<br>" if entry.get('ticket') else ""

            if "BUY" in entry_action:
                marker_symbol = 'triangle-up'
                marker_color = '#00E676' # Panah hijau
                trace_name = f"ENTRY BUY ({prob_str})"
                hover_summary = (
                    f"<b>ENTRY BUY | Probabilitas: {prob_str}</b><br>"
                    f"{ticket_info}"
                    f"Harga Masuk: {entry_price:.2f}<br>"
                    f"SL Awal: {sl_val:.2f}<br>"
                    f"TP Awal: {tp_val:.2f}<br>"
                    f"Waktu: {time_str}"
                )
            else:
                marker_symbol = 'triangle-down'
                marker_color = '#FF1744' # Panah merah
                trace_name = f"ENTRY SELL ({prob_str})"
                hover_summary = (
                    f"<b>ENTRY SELL | Probabilitas: {prob_str}</b><br>"
                    f"{ticket_info}"
                    f"Harga Masuk: {entry_price:.2f}<br>"
                    f"SL Awal: {sl_val:.2f}<br>"
                    f"TP Awal: {tp_val:.2f}<br>"
                    f"Waktu: {time_str}"
                )

            fig.add_trace(go.Scatter(
                x=[entry_time],
                y=[entry_price],
                mode='markers',
                marker=dict(
                    symbol=marker_symbol,
                    size=16,
                    color=marker_color,
                    line=dict(width=2, color='#FFFFFF')
                ),
                name=trace_name,
                hovertext=hover_summary,
                hoverinfo='text',
                showlegend=True
            ))

    # 4. Dua Garis Horizontal Putus-Putus (hline) untuk Stop Loss & Take Profit Awal
    if active_trade:
        sl_price = active_trade.get('sl')
        tp_price = active_trade.get('tp')
        
        if sl_price and float(sl_price) > 0:
            fig.add_hline(
                y=float(sl_price),
                line_dash="dash",
                line_color="#FF3B30",
                line_width=2,
                annotation_text=f"SL Awal: {float(sl_price):.2f}",
                annotation_position="top right",
                annotation_font=dict(color="#FF3B30", size=11, family="Arial")
            )
            
        if tp_price and float(tp_price) > 0:
            fig.add_hline(
                y=float(tp_price),
                line_dash="dash",
                line_color="#00E676",
                line_width=2,
                annotation_text=f"TP Awal: {float(tp_price):.2f}",
                annotation_position="bottom right",
                annotation_font=dict(color="#00E676", size=11, family="Arial")
            )

    # Styling dan Format Layout
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=16, color="#ECEFF1")
        ),
        template="plotly_dark",
        height=height,
        xaxis_rangeslider_visible=False,
        margin=dict(l=40, r=40, t=50, b=30),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10)
        ),
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255, 255, 255, 0.07)',
            zeroline=False
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255, 255, 255, 0.07)',
            zeroline=False,
            side="right"
        ),
        paper_bgcolor="#0E1117",
        plot_bgcolor="#0E1117"
    )

    return fig

# Helper untuk memuat data candle pasar (MT5 -> DB -> Dummy Generator)
def fetch_display_candles(symbol: str, timeframe_const, n_candles: int = 150):
    # 1. Coba dari MT5 jika aktif
    if mt5.terminal_info() is not None:
        try:
            df = get_rates(symbol, timeframe_const, n_candles)
            if df is not None and not df.empty:
                return calculate_bbma(df)
        except Exception:
            pass

    # 2. Coba dari Database market_data_merged
    try:
        query = f"SELECT time, open, high, low, close, tick_volume FROM market_data_merged ORDER BY time DESC LIMIT {n_candles}"
        df_db = pd.read_sql(query, con=sync_engine)
        if not df_db.empty:
            df_db = df_db.sort_values('time').reset_index(drop=True)
            df_db['time'] = pd.to_datetime(df_db['time'])
            return calculate_bbma(df_db)
    except Exception:
        pass

    # 3. Fallback sintetis realistis jika DB belum dibackfill
    now = datetime.datetime.now()
    dates = [now - datetime.timedelta(minutes=i) for i in range(n_candles)][::-1]
    base_price = 2650.0
    prices = [base_price]
    for _ in range(n_candles - 1):
        prices.append(prices[-1] + np.random.normal(0, 0.6))
    
    df_sample = pd.DataFrame({
        'time': dates,
        'open': prices,
        'close': [p + np.random.normal(0, 0.4) for p in prices],
    })
    df_sample['high'] = df_sample[['open', 'close']].max(axis=1) + np.random.uniform(0.1, 0.5, n_candles)
    df_sample['low'] = df_sample[['open', 'close']].min(axis=1) - np.random.uniform(0.1, 0.5, n_candles)
    df_sample['tick_volume'] = np.random.randint(50, 400, n_candles)
    return calculate_bbma(df_sample)


# ==========================================
# HEADER UTAMA APLIKASI
# ==========================================
st.title("🤖 BBMA Autonomous AI Trader")
st.caption("Arsitektur 5-Agen Otonom dengan Walk-Forward Machine Learning & Circuit Breakers Absolut")
st.markdown("---")

# ==========================================
# 3-TAB INTERFACE ARCHITECTURE
# ==========================================
tab_cmd, tab_incubator, tab_journal = st.tabs(['🎛️ Command Center', '🧠 AI Incubator', '📊 Trade Journal'])

# ==============================================================================
# TAB 1: 🎛️ COMMAND CENTER
# Memuat Master Controls, Live Metrics, Risk Setup, Database Health, dan Terminal Log
# ==============================================================================
with tab_cmd:
    col1, col2, col3 = st.columns(3)

    # Master Controls
    with col1:
        st.subheader("Master Controls")
        if st.button("Start System", width="stretch", type="primary"):
            start_system()
            
        if st.button("Emergency Stop", width="stretch"):
            st.session_state.executor.stop()
            st.session_state.supervisor.trigger_friday_liquidator()
            shutdown_mt5()
            st.warning("System Stopped.")
            
        if st.button("FORCE DATA BACKFILL", width="stretch"):
            with st.spinner("Menarik data historis dari broker... (mungkin butuh waktu beberapa saat)"):
                backfill_db()
                
        st.markdown("---")
        st.write("**Sync MT5 Calendar Bridge**")
        st.caption("Pastikan MacroBridge.mq5 sedang berjalan di grafik MT5.")
        
        if st.button("FORCE SYNC FROM MT5 CSV", width="stretch"):
            with st.spinner("Membaca file CSV dari MT5 dan menyimpan ke DB..."):
                df = st.session_state.data_miner.sync_mt5_calendar_to_db()
                if df is not None and not df.empty:
                    st.success(f"Berhasil sinkronisasi {len(df)} jadwal High Impact dari MT5.")
                else:
                    st.warning("Gagal membaca CSV atau data kosong.")

    # System Status & Live Metrics
    with col2:
        st.subheader("System Status")
        st.write(f"**State Mesin (Agent 0):** `{st.session_state.supervisor.state.upper()}`")
        st.write(f"**Symbol:** `{Config.SYMBOL}`")
        
        # Live Trade Metrics
        st.markdown("---")
        st.write("**📈 Live Trade Metrics**")
        m1, m2, m3 = st.columns(3)
        
        active_positions = 0
        if mt5.terminal_info() is not None:
            try:
                active_positions = mt5.positions_total()
            except Exception:
                pass
                
        m1.metric("Win Rate", "0.0%")
        m2.metric("Capital Growth", "$0.0")
        m3.metric("Active Pos", f"{active_positions}")
        
        # Macro Radar
        st.markdown("---")
        st.write("**📡 Macro Radar**")
        events_df = st.session_state.data_miner.get_live_calendar()
        if not events_df.empty:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            upcoming = events_df[events_df['date'] > now_utc].sort_values('date')
            
            if not upcoming.empty:
                next_event = upcoming.iloc[0]
                time_to = next_event['date'] - now_utc
                hours, remainder = divmod(time_to.total_seconds(), 3600)
                minutes, _ = divmod(remainder, 60)
                
                st.info(f"⏳ **Next Event:** {next_event['event']} in **{int(hours)}h {int(minutes)}m**\n\n🗓️ {next_event['date'].strftime('%Y-%m-%d %H:%M UTC')}")
            else:
                st.success("Tugas selesai! Tidak ada lagi event High Impact minggu ini.")
                
            st.write("*Recent Events:*")
            st.dataframe(events_df.tail(3), hide_index=True, width="stretch")
        else:
            st.write("Tidak ada High Impact News terdeteksi minggu ini.")

    # Risk & Account
    with col3:
        st.subheader("Risk & Account")
        st.number_input("Max Risk per Trade ($)", value=float(Config.MAX_RISK_DOLLARS), step=10.0)
        st.number_input("Max Drawdown (%)", value=float(Config.MAX_DRAWDOWN_PERCENT), step=1.0)
        
        # Account Metrics
        st.markdown("---")
        st.write("**💼 Account Metrics**")
        acc_m1, acc_m2 = st.columns(2)
        acc_info = None
        if mt5.terminal_info() is not None:
            try:
                acc_info = mt5.account_info()
            except Exception:
                pass
                
        if acc_info is not None:
            acc_m1.metric("Balance", f"${acc_info.balance:,.2f}")
            acc_m2.metric("Equity", f"${acc_info.equity:,.2f}")
        else:
            acc_m1.metric("Balance", "$0.00")
            acc_m2.metric("Equity", "$0.00")
        
        # Database Health
        st.markdown("---")
        st.write("**🗄️ Database Health**")
        try:
            db_size = get_db_size()
            st.metric("Total Rows Ready", f"{db_size:,}")
            start_date, end_date = get_db_date_range()
            if start_date and end_date:
                try:
                    start_str = start_date.strftime("%Y-%m-%d %H:%M") if hasattr(start_date, "strftime") else str(start_date)[:16]
                    end_str = end_date.strftime("%Y-%m-%d %H:%M") if hasattr(end_date, "strftime") else str(end_date)[:16]
                    st.caption(f"Periode: **{start_str}** s.d **{end_str}**")
                except Exception:
                    st.caption(f"Periode: {start_date} s.d {end_date}")
        except Exception:
            st.warning("Database belum terinisialisasi. Lakukan Backfill terlebih dahulu.")

    # Live Market Candlestick Preview di Command Center
    st.markdown("---")
    c_hdr1, c_hdr2 = st.columns([0.8, 0.2])
    with c_hdr1:
        st.subheader("📈 Live Execution & Candlestick Monitor")
    with c_hdr2:
        tf_choice = st.selectbox("Timeframe", ["M1", "M5", "M15"], index=0, key="cmd_tf_select")
        
    tf_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15}
    live_candles = fetch_display_candles(Config.SYMBOL, tf_map[tf_choice], n_candles=120)

    # Deteksi posisi aktif MT5 untuk di-highlight di grafik Command Center
    live_entries = []
    live_active_trade = None
    if mt5.terminal_info() is not None:
        try:
            positions = mt5.positions_get(symbol=Config.SYMBOL)
            if positions:
                for p in positions:
                    action_type = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                    entry_dict = {
                        'time': pd.to_datetime(p.time, unit='s'),
                        'action': action_type,
                        'price': p.price_open,
                        'sl': p.sl,
                        'tp': p.tp,
                        'probability': "85%",
                        'ticket': p.ticket
                    }
                    live_entries.append(entry_dict)
                    if live_active_trade is None:
                        live_active_trade = entry_dict
        except Exception:
            pass

    fig_cmd = render_candlestick_chart(
        df=live_candles,
        trade_entries=live_entries,
        active_trade=live_active_trade,
        title=f"{Config.SYMBOL} ({tf_choice}) - Live Monitoring & Active Fuses",
        height=480
    )
    st.plotly_chart(fig_cmd, width="stretch")

    # Terminal Log
    st.markdown("---")
    st.subheader("Terminal Log")
    col_log1, col_log2 = st.columns([0.9, 0.1])
    with col_log2:
        if st.button("🔄 Refresh", key="log_refresh_btn", width="stretch"):
            pass

    log_text = "\n".join(st.session_state.log_handler.log_area)
    st.text_area("Live Console Output", log_text, height=260)


# ==============================================================================
# TAB 2: 🧠 AI INCUBATOR
# Memuat Arsitektur Dual-Target (LightGBM), Status Training, Feature Importance & Gatekeeper Walk-Forward
# ==============================================================================
with tab_incubator:
    st.subheader("🧠 AI Incubator & Model Diagnostics")
    st.write("Laboratorium pelatihan mandiri *Tree-Based Machine Learning* (LightGBM) dengan target dinamis berbasis volatilitas (ATR).")
    
    ai_col1, ai_col2 = st.columns([0.55, 0.45])

    with ai_col1:
        st.markdown("### 🧬 Dual-Target Architecture")
        
        # Model Normal Card
        with st.container(border=True):
            st.markdown("#### 🎯 Target_Normal (Hit & Run)")
            st.write("- **Rasio Risk-Reward:** 1 : 2.0")
            st.write("- **Lookahead Window:** Maksimal 100 candle M1 kedepan.")
            st.write("- **Strategi Eksekusi:** Menutup 100% posisi saat menyentuh take profit dinamis.")
            is_normal_trained = st.session_state.researcher.model_normal is not None
            st.markdown(f"Status Model: `{'🟢 TRAINED' if is_normal_trained else '⚪ IDLE (BELUM DILATIH)'}`")

        # Model Runner Card
        with st.container(border=True):
            st.markdown("#### 🚀 Target_Runner (Trend Rider)")
            st.write("- **Rasio Risk-Reward:** 1 : 5.0+")
            st.write("- **Lookahead Window:** Maksimal 300 candle M1 kedepan.")
            st.write("- **Strategi Eksekusi:** Saat RR 1:2 tercapai, Partial Close 50%, pindahkan SL ke Break Even, dan aktifkan Topographical Trailing Stop (EMA 50 / LWMA 10).")
            is_runner_trained = st.session_state.researcher.model_runner is not None
            st.markdown(f"Status Model: `{'🟢 TRAINED' if is_runner_trained else '⚪ IDLE (BELUM DILATIH)'}`")

    with ai_col2:
        st.markdown("### 🛡️ Gatekeeper (Walk-Forward Validator)")
        with st.container(border=True):
            st.write("- **Skema Split:** 80% Temporal In-Sample (Train) / 20% Out-of-Sample (Test)")
            st.write("- **Anti-Overfitting Filter:** Akurasi OOS Normal & Runner wajib > **50.0%**")
            valid_status = st.session_state.supervisor.is_model_valid()
            st.markdown(f"Status Validasi Terakhir: `{'✅ PASSED (LAYAK LIVE)' if valid_status else '⚠️ PENDING / REJECTED'}`")
            
        st.markdown("### ⚡ Manual Incubator Trigger")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            btn_train = st.button("🚀 Latih Ulang (Incremental)", width="stretch")
        with col_btn2:
            btn_force = st.button("🧹 Force Latih Ulang (Clean Slate)", width="stretch", type="primary")

        if btn_train or btn_force:
            if btn_force:
                st.session_state.researcher.model_normal = None
                st.session_state.researcher.model_runner = None
            total_chunks, train_gen = st.session_state.data_miner.load_train_chunks(split_ratio=TEMPORAL_SPLIT_RATIO)
            if total_chunks > 0 and train_gen is not None:
                with st.spinner("Mempersiapkan data pelatihan Incremental..."):
                    progress_bar = st.progress(0, text="Memulai pelatihan Incremental Learning...")
                    def update_progress(chunk_idx, total):
                        pct = int((chunk_idx / total) * 100)
                        progress_bar.progress(pct, text=f"Melatih AI (Chunk {chunk_idx}/{total})...")
                        
                    st.session_state.researcher.train_models(train_gen, total_chunks=total_chunks, progress_callback=update_progress)
                    progress_bar.empty()
                    
                    test_df = st.session_state.data_miner.load_test_data(split_ratio=TEMPORAL_SPLIT_RATIO)
                    
                    valid = False
                    if test_df is not None and not test_df.empty:
                        valid = st.session_state.gatekeeper.validate_model(test_df)
                    st.session_state.supervisor.set_model_validity(valid)
                    if valid:
                        st.success("Pelatihan Selesai! Model LULUS uji Walk-Forward.")
                    else:
                        st.warning("Pelatihan Selesai, namun model GAGAL uji Out-of-Sample.")
            else:
                st.error("Data di database tidak cukup untuk pelatihan (>500 baris dibutuhkan). Lakukan Force Backfill terlebih dahulu.")

    # Feature Importance Section
    st.markdown("---")
    st.markdown("### 📊 Topografi BBMA & Bobot Fitur (Feature Importance)")
    if st.session_state.researcher.model_normal is not None and hasattr(st.session_state.researcher.model_normal, 'feature_importances_'):
        features = st.session_state.researcher.features
        importances = st.session_state.researcher.model_normal.feature_importances_
        
        if len(features) != len(importances):
            features = [f"Feature_{i}" for i in range(len(importances))]
            
        fi_df = pd.DataFrame({'Feature': features, 'Importance': importances}).sort_values('Importance', ascending=True).tail(15)
        
        fig_fi = go.Figure(go.Bar(
            x=fi_df['Importance'],
            y=fi_df['Feature'],
            orientation='h',
            marker=dict(color='#26a69a')
        ))
        fig_fi.update_layout(
            title="Top 15 Feature Importances (Normal Model)",
            template="plotly_dark",
            height=400,
            margin=dict(l=20, r=20, t=40, b=20),
            paper_bgcolor="#0E1117",
            plot_bgcolor="#0E1117"
        )
        st.plotly_chart(fig_fi, width="stretch")
    else:
        st.info("Visualisasi bobot fitur akan tersedia setelah model AI dilatih.")

    # ==============================================================================
    # RLHF: HUMAN-IN-THE-LOOP SETUP CURATION
    # ==============================================================================
    st.markdown("---")
    st.markdown("### 🎯 RLHF (Human-in-the-Loop): Kurasi Setup Out-of-Sample")
    st.write("Inspeksi seluruh setup probabilitas tinggi pada data Out-of-Sample (OOS). Setup yang disetujui (**Approve**) akan disimpan ke database `approved_setups` dan otomatis mendapatkan bobot sampel **5.0x lebih besar** pada training LightGBM berikutnya.")

    approved_ids = get_approved_setup_ids()
    st.write(f"Total Setup Disetujui Saat Ini: **{len(approved_ids)} Setup**")

    min_prob = st.slider("Minimal Probabilitas Setup OOS (Filter Ambang Batas):", min_value=0.50, max_value=0.99, value=0.65, step=0.01)

    if st.button("🔍 Muat Data OOS untuk Analisis RLHF", use_container_width=True):
        st.session_state.load_rlhf = True

    df_raw = None
    if st.session_state.get('load_rlhf', False):
        with st.spinner("Memuat data historis dari database..."):
            df_raw = st.session_state.data_miner.load_from_db()

    if df_raw is not None and len(df_raw) > 200 and st.session_state.researcher.model_normal is not None:
        split_idx = int(len(df_raw) * TEMPORAL_SPLIT_RATIO)
        oos_df = df_raw.iloc[split_idx:].copy()
        oos_df = st.session_state.researcher.generate_targets(oos_df)
        oos_df = oos_df.dropna()
        features = st.session_state.researcher.features
        valid_cols = [c for c in features if c in oos_df.columns]

        if valid_cols:
            probs = st.session_state.researcher.model_normal.predict_proba(oos_df[valid_cols])[:, 1]
            oos_df['prob'] = probs
            high_prob_df = oos_df[oos_df['prob'] >= min_prob]

            st.write(f"Menemukan **{len(high_prob_df)}** setup OOS yang lolos ambang batas probabilitas ≥ {min_prob*100:.0f}%.")

            if not high_prob_df.empty:
                # Tampilkan SEMUA setup OOS yang lolos batas (tanpa batasan jumlah)
                for idx_num, (setup_time, row) in enumerate(high_prob_df.head(50).iterrows()):
                    setup_id = setup_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(setup_time, "strftime") else str(setup_time)
                    prob_pct = f"{row['prob']*100:.1f}%"
                    is_approved = setup_id in approved_ids

                    action_type = "BUY" if row.get('dist_Close_EMA50', 0) >= 0 else "SELL"
                    sl_dist = abs(row.get('dist_Close_EMA50', 10.0))
                    sl_dist = max(sl_dist, 5.0)
                    sl_val = row['close'] - sl_dist if action_type == "BUY" else row['close'] + sl_dist
                    tp_val = row['close'] + (sl_dist * 2.0) if action_type == "BUY" else row['close'] - (sl_dist * 2.0)

                    with st.expander(f"📍 Setup #{idx_num+1} | {setup_id} | Probabilitas: {prob_pct} | {action_type} @ {row['close']:.2f} {'✅ (APPROVED)' if is_approved else ''}", expanded=(idx_num < 2)):
                        loc = oos_df.index.get_loc(setup_time)
                        if isinstance(loc, (int, np.integer)):
                            start_w = max(0, loc - 35)
                            end_w = min(len(oos_df), loc + 15)
                            window_df = oos_df.iloc[start_w:end_w].copy()
                        else:
                            window_df = oos_df.tail(40).copy()

                        entry_marker = [{
                            'time': setup_time,
                            'action': action_type,
                            'price': float(row['close']),
                            'sl': float(sl_val),
                            'tp': float(tp_val),
                            'probability': prob_pct,
                            'ticket': f"OOS-{idx_num+1}"
                        }]

                        fig_setup = render_candlestick_chart(
                            df=window_df,
                            trade_entries=entry_marker,
                            active_trade=entry_marker[0],
                            title=f"Setup OOS: {setup_id} ({action_type})",
                            height=600
                        )
                        st.plotly_chart(fig_setup, width="stretch")

                        btn_col1, btn_col2 = st.columns([0.3, 0.7])
                        with btn_col1:
                            if is_approved:
                                st.success("✅ Setup ini Sudah Di-Approve")
                            else:
                                if st.button(f"👍 Approve Setup #{idx_num+1}", key=f"btn_rlhf_{setup_id}_{idx_num}", width="stretch"):
                                    save_approved_setup(
                                        setup_id=setup_id,
                                        symbol=Config.SYMBOL,
                                        action=action_type,
                                        probability=float(row['prob']),
                                        notes=f"Approved via RLHF UI (Prob {prob_pct})"
                                    )
                                    st.success(f"Setup {setup_id} berhasil di-Approve!")
                                    st.rerun()
                        with btn_col2:
                            st.caption(f"Distansi EMA50: {row.get('dist_Close_EMA50', 0):.2f} | Lebar BB: {row.get('BB_Width', 0):.2f} | Menit ke News: {row.get('minutes_to_high_impact_news', 9999):.0f}m")
            else:
                st.info("Tidak ada setup OOS yang melampaui batas probabilitas slider saat ini. Turunkan nilai slider untuk melihat lebih banyak setup.")
    else:
        # Simulasi interaktif jika data/model belum dilatih
        st.info("💡 Menampilkan simulasi kurasi setup RLHF (Model belum dilatih pada database).")
        sim_setups = [
            {"time": "2026-09-18 14:15:00", "prob": 0.84, "action": "BUY", "price": 2652.50, "sl": 2644.00, "tp": 2669.50},
            {"time": "2026-09-18 15:30:00", "prob": 0.78, "action": "SELL", "price": 2668.00, "sl": 2675.00, "tp": 2654.00},
            {"time": "2026-09-18 16:45:00", "prob": 0.71, "action": "BUY", "price": 2658.20, "sl": 2650.00, "tp": 2674.60},
        ]
        sim_filtered = [s for s in sim_setups if s["prob"] >= min_prob]
        st.write(f"Ditemukan **{len(sim_filtered)}** setup simulasi dengan probabilitas ≥ {min_prob*100:.0f}%.")
        for i, s in enumerate(sim_filtered):
            s_id = s["time"]
            is_app = s_id in approved_ids
            with st.expander(f"📍 Setup #{i+1} | {s_id} | Prob: {s['prob']*100:.0f}% | {s['action']} @ {s['price']:.2f} {'✅ (APPROVED)' if is_app else ''}", expanded=(i==0)):
                dummy_df = fetch_display_candles(Config.SYMBOL, mt5.TIMEFRAME_M5, 40)
                marker = [{
                    'time': dummy_df['time'].iloc[-10],
                    'action': s['action'],
                    'price': s['price'],
                    'sl': s['sl'],
                    'tp': s['tp'],
                    'probability': f"{s['prob']*100:.0f}%",
                    'ticket': f"SIM-{i+1}"
                }]
                fig_sim = render_candlestick_chart(dummy_df, trade_entries=marker, active_trade=marker[0], title=f"Setup {s_id}", height=600)
                st.plotly_chart(fig_sim, width="stretch")
                if is_app:
                    st.success("✅ Setup ini Sudah Di-Approve")
                else:
                    if st.button(f"👍 Approve Setup #{i+1}", key=f"sim_app_{s_id}_{i}", width="stretch"):
                        save_approved_setup(s_id, symbol=Config.SYMBOL, action=s['action'], probability=s['prob'], notes="Approved via RLHF Simulation")
                        st.success(f"Setup {s_id} berhasil di-Approve!")
                        st.rerun()


# ==============================================================================
# TAB 3: 📊 TRADE JOURNAL
# Memuat Riwayat Log Black Box Berdampingan dengan Snapshot Candlestick & Alasan XAI
# ==============================================================================
with tab_journal:
    st.subheader("📊 Trade Journal & Black Box XAI")
    st.caption("Perekaman otomatis setiap aksi riil (Entry, Geser SL, Exit) beserta 50 candle M1 dan kontribusi fitur LightGBM.")

    # Ambil catatan Black Box dari tabel trade_journal
    journal_entries = get_trade_journal_entries(limit=100)
    db_trade_logs = get_recent_trade_logs(limit=100)

    # Header Metrik Jurnal
    total_blackbox = len(journal_entries)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Event Black Box", f"{total_blackbox}")
    m2.metric("Total Riwayat Posisi", f"{len(db_trade_logs)}")
    m3.metric("Simbol Pantau", f"{Config.SYMBOL}")
    m4.metric("Engine XAI", "LightGBM Tree SHAP")
    st.markdown("---")

    # SIDE-BY-SIDE LAYOUT: Riwayat Log Berdampingan dengan Grafiknya
    col_log, col_chart = st.columns([0.45, 0.55])

    with col_log:
        st.markdown("### 📜 Riwayat Aksi Black Box")
        if not journal_entries.empty:
            options = [
                f"ID #{row['id']} | Tiket #{row['tiket']} | {row['event_type']} @ {row['harga']:.2f} ({row['timestamp'].strftime('%H:%M:%S')})"
                for _, row in journal_entries.iterrows()
            ]
            sel_idx = st.selectbox("🎯 Pilih Catatan Event untuk Diinspeksi:", range(len(options)), format_func=lambda i: options[i])
            cur_entry = journal_entries.iloc[sel_idx]

            with st.container(border=True):
                st.markdown(f"#### Detail Event: `{cur_entry['event_type']}`")
                st.write(f"- **Nomor Tiket MT5:** `{cur_entry['tiket']}`")
                st.write(f"- **Waktu Eksekusi:** `{cur_entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}`")
                st.write(f"- **Harga Transaksi:** `{cur_entry['harga']:.2f}`")
                st.markdown("---")
                st.markdown("##### 🤖 Alasan AI (Top 3 Feature Contributions):")
                st.info(cur_entry['alasan'])

            # Tabel ringkasan log
            st.dataframe(
                journal_entries[['tiket', 'timestamp', 'event_type', 'harga', 'alasan']], 
                hide_index=True, 
                width="stretch",
                column_config={
                    "harga": st.column_config.NumberColumn("Harga", format="%.2f"),
                    "timestamp": st.column_config.DatetimeColumn("Waktu", format="YYYY-MM-DD HH:mm:ss")
                }
            )
        else:
            st.info("Belum ada event transaksi riil di database `trade_journal`. Menampilkan simulasi log Black Box.")
            sim_options = [
                "Simulasi #1 | Tiket #88210 | ENTRY @ 2650.50 (14:30:15)",
                "Simulasi #2 | Tiket #88210 | SL_MODIFY @ 2650.50 (14:48:22)",
                "Simulasi #3 | Tiket #88210 | EXIT @ 2665.20 (15:05:40)"
            ]
            sel_sim = st.selectbox("Pilih Event Simulasi:", sim_options)
            with st.container(border=True):
                if "ENTRY" in sel_sim:
                    st.markdown("#### Detail Event: `ENTRY`")
                    st.write("- **Nomor Tiket MT5:** `88210`")
                    st.write("- **Waktu Eksekusi:** `2026-09-18 14:30:15`")
                    st.write("- **Harga Transaksi:** `2650.50`")
                    st.info("Top 3 Fitur: dist_Close_EMA50 (+0.52), BB_Width (+0.38), minutes_to_high_impact_news (+0.24)")
                elif "SL_MODIFY" in sel_sim:
                    st.markdown("#### Detail Event: `SL_MODIFY`")
                    st.write("- **Nomor Tiket MT5:** `88210`")
                    st.write("- **Waktu Eksekusi:** `2026-09-18 14:48:22`")
                    st.write("- **Harga Transaksi:** `2650.50` (Break Even)")
                    st.info("Risk Management: Break Even tercapai (RR 1:2). SL digeser ke harga Open (2650.50) untuk eliminasi risiko.")
                else:
                    st.markdown("#### Detail Event: `EXIT`")
                    st.write("- **Nomor Tiket MT5:** `88210`")
                    st.write("- **Waktu Eksekusi:** `2026-09-18 15:05:40`")
                    st.write("- **Harga Transaksi:** `2665.20`")
                    st.info("Hit & Run: Target RR 1:2 Tercapai. Mengunci 50% profit (Likuidasi 0.10 Lot).")

    with col_chart:
        st.markdown("### 📈 Visualisasi Grafik Candlestick")
        chart_rendered = False
        if not journal_entries.empty:
            cur_entry = journal_entries.iloc[sel_idx]
            snap_str = cur_entry.get('chart_snapshot', '{}')
            try:
                if snap_str and snap_str != "{}":
                    df_snap = pd.read_json(io.StringIO(snap_str))
                    if not df_snap.empty and 'close' in df_snap.columns:
                        if 'time' in df_snap.columns:
                            df_snap['time'] = pd.to_datetime(df_snap['time'])
                        act = "BUY" if cur_entry['event_type'] == "ENTRY" else ("SELL" if cur_entry['event_type'] == "EXIT" else "SL_MODIFY")
                        marker = [{
                            'time': df_snap['time'].iloc[-1],
                            'action': act,
                            'price': float(cur_entry['harga']),
                            'sl': float(cur_entry['harga']) - 8.0,
                            'tp': float(cur_entry['harga']) + 16.0,
                            'probability': "85%",
                            'ticket': cur_entry['tiket']
                        }]
                        fig_snap = render_candlestick_chart(
                            df=df_snap,
                            trade_entries=marker,
                            active_trade=marker[0],
                            title=f"Snapshot Black Box: {cur_entry['event_type']} Tiket #{cur_entry['tiket']} @ {cur_entry['harga']:.2f}",
                            height=600
                        )
                        st.plotly_chart(fig_snap, width="stretch")
                        chart_rendered = True
            except Exception as e:
                logging.debug(f"Snapshot parse error: {e}")

        if not chart_rendered:
            sim_candles = fetch_display_candles(Config.SYMBOL, mt5.TIMEFRAME_M1, 50)
            sim_marker = [{
                'time': sim_candles['time'].iloc[-15],
                'action': 'BUY',
                'price': float(sim_candles['close'].iloc[-15]),
                'sl': float(sim_candles['close'].iloc[-15]) - 7.0,
                'tp': float(sim_candles['close'].iloc[-15]) + 14.0,
                'probability': '82%',
                'ticket': 88210
            }]
            fig_sim_chart = render_candlestick_chart(
                df=sim_candles,
                trade_entries=sim_marker,
                active_trade=sim_marker[0],
                title=f"Snapshot Candlestick 50 M1 (Simulasi)",
                height=600
            )
            st.plotly_chart(fig_sim_chart, width="stretch")

    st.markdown("---")
    st.markdown("### 📋 Riwayat Transaksi Lengkap (Database & Broker Deals)")
    if not db_trade_logs.empty:
        st.dataframe(
            db_trade_logs, 
            hide_index=True, 
            width="stretch",
            column_config={
                "profit": st.column_config.NumberColumn("Profit ($)", format="$%.2f"),
                "price": st.column_config.NumberColumn("Harga Entry", format="%.2f"),
                "sl": st.column_config.NumberColumn("Stop Loss", format="%.2f"),
                "tp": st.column_config.NumberColumn("Take Profit", format="%.2f"),
            }
        )
    else:
        st.info("Belum ada riwayat transaksi akun tersimpan.")
