import streamlit as st
import threading
import asyncio
import logging
import MetaTrader5 as mt5
from config import Config
from utils.mt5_utils import init_mt5, shutdown_mt5
from database import get_db_size, get_db_date_range

from agents.supervisor import SupervisorAgent
from agents.data_miner import DataMinerAgent
from agents.researcher import ResearcherAgent
from agents.gatekeeper import GatekeeperAgent
from agents.executor import ExecutorAgent

st.set_page_config(page_title="BBMA AI Trader", layout="wide")

# Custom Logger for Streamlit
class StreamlitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_area = []

    def emit(self, record):
        msg = self.format(record)
        self.log_area.append(msg)
        if len(self.log_area) > 100:
            self.log_area.pop(0)

if 'log_handler' not in st.session_state:
    st.session_state.log_handler = StreamlitLogHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    st.session_state.log_handler.setFormatter(formatter)
    
    # Avoid duplicate handlers if reloading
    if not any(isinstance(h, StreamlitLogHandler) for h in logging.getLogger().handlers):
        logging.getLogger().addHandler(st.session_state.log_handler)
        logging.getLogger().setLevel(logging.INFO)

# Global state
if 'supervisor' not in st.session_state:
    st.session_state.supervisor = SupervisorAgent()
    st.session_state.data_miner = DataMinerAgent(symbol=Config.SYMBOL)
    st.session_state.researcher = ResearcherAgent()
    st.session_state.gatekeeper = GatekeeperAgent(st.session_state.researcher)
    st.session_state.executor = ExecutorAgent(st.session_state.supervisor)
    st.session_state.executor_thread = None

def start_executor_loop(executor):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(executor.monitor_market())

def start_system():
    # Inisialisasi MT5
    if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD, Config.MT5_PATH):
        st.success("Terkoneksi ke MT5")
        
        st.session_state.supervisor.start_ingestion()
        df = st.session_state.data_miner.load_from_db()
        
        if df is not None and not df.empty:
            # Temporal Train-Test Split (75% / 25%)
            split_idx = int(len(df) * 0.75)
            train_df = df.iloc[:split_idx]
            test_df = df.iloc[split_idx:]
            
            st.session_state.supervisor.start_research()
            st.session_state.researcher.train_models(train_df)
            
            st.session_state.supervisor.start_evaluation()
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
        count = st.session_state.data_miner.backfill_data(5000000) # Maksimal ditarik semua data yang tersedia di broker
        st.success(f"Backfill berhasil! Menyimpan {count} baris data.")

st.title("🤖 BBMA Autonomous AI Trader")
st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Master Controls")
    if st.button("Start System"):
        start_system()
        
    if st.button("Emergency Stop"):
        st.session_state.executor.stop()
        st.session_state.supervisor.trigger_friday_liquidator()
        shutdown_mt5()
        st.warning("System Stopped.")
        
    if st.button("FORCE DATA BACKFILL", type="primary"):
        with st.spinner("Menarik data historis dari broker... (mungkin butuh waktu beberapa saat)"):
            backfill_db()

with col2:
    st.subheader("System Status")
    st.write(f"**State Mesin (Agent 0):** {st.session_state.supervisor.state.upper()}")
    st.write(f"**Symbol:** {Config.SYMBOL}")
    
    # Live Trade Metrics
    st.markdown("---")
    st.write("**📈 Live Trade Metrics**")
    m1, m2, m3 = st.columns(3)
    
    # Coba dapatkan total posisi, asumsikan 0 jika gagal koneksi
    active_positions = 0
    if mt5.terminal_info() is not None:
        try:
            active_positions = mt5.positions_total()
        except:
            pass
            
    m1.metric("Win Rate", "0.0%")
    m2.metric("Capital Growth", "$0.0")
    m3.metric("Active Pos", f"{active_positions}")
    
    # Macro Radar
    st.markdown("---")
    st.write("**📡 Macro Radar**")
    events_df = st.session_state.data_miner.fetch_economic_calendar()
    if not events_df.empty:
        st.dataframe(events_df.head(3), hide_index=True)
    else:
        st.write("Tidak ada High Impact News terdeteksi minggu ini.")

with col3:
    st.subheader("Risk & Account")
    st.number_input("Max Risk per Trade ($)", value=Config.MAX_RISK_DOLLARS)
    st.number_input("Max Drawdown (%)", value=Config.MAX_DRAWDOWN_PERCENT)
    
    # Account Metrics
    st.markdown("---")
    st.write("**💼 Account Metrics**")
    acc_m1, acc_m2 = st.columns(2)
    acc_info = None
    if mt5.terminal_info() is not None:
        try:
            acc_info = mt5.account_info()
        except:
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
            # Format output to a readable string (YYYY-MM-DD HH:MM)
            try:
                start_str = start_date.strftime("%Y-%m-%d %H:%M") if hasattr(start_date, "strftime") else str(start_date)[:16]
                end_str = end_date.strftime("%Y-%m-%d %H:%M") if hasattr(end_date, "strftime") else str(end_date)[:16]
                st.caption(f"Periode Data: **{start_str}** s.d **{end_str}**")
            except:
                st.caption(f"Periode Data: {start_date} s.d {end_date}")
    except Exception as e:
        st.warning(f"Database belum terinisialisasi. Lakukan Backfill terlebih dahulu.")

st.markdown("---")
st.subheader("Terminal Log")
col_log1, col_log2 = st.columns([0.9, 0.1])
with col_log2:
    if st.button("🔄 Refresh"):
        pass

log_text = "\n".join(st.session_state.log_handler.log_area)
st.text_area("Live Console Output", log_text, height=300)
