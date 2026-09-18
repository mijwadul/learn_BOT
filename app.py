import streamlit as st
import threading
import asyncio
import logging
from config import Config
from utils.mt5_utils import init_mt5, shutdown_mt5
from database import get_db_size

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
    if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD):
        st.success("Terkoneksi ke MT5")
        
        st.session_state.supervisor.start_ingestion()
        df = st.session_state.data_miner.fetch_and_merge_data()
        
        if df is not None:
            st.session_state.supervisor.start_research()
            st.session_state.researcher.train_models(df)
            
            st.session_state.supervisor.start_evaluation()
            valid = st.session_state.gatekeeper.validate_model(df.tail(200)) # OOS dummy
            
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
    if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD):
        count = st.session_state.data_miner.backfill_data(10000)
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
    
    # Macro Radar
    st.markdown("---")
    st.write("**📡 Macro Radar**")
    events_df = st.session_state.data_miner.fetch_economic_calendar()
    if not events_df.empty:
        st.dataframe(events_df.head(3), hide_index=True)
    else:
        st.write("Tidak ada High Impact News terdeteksi minggu ini.")

with col3:
    st.subheader("Risk Setup")
    st.number_input("Max Risk per Trade ($)", value=Config.MAX_RISK_DOLLARS)
    st.number_input("Max Drawdown (%)", value=Config.MAX_DRAWDOWN_PERCENT)
    
    # Database Health
    st.markdown("---")
    st.write("**🗄️ Database Health**")
    try:
        db_size = get_db_size()
        st.metric("Total Rows Ready", f"{db_size:,}")
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
