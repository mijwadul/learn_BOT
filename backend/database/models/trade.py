from sqlalchemy import Column, Integer, String, Float, DateTime, Text, BigInteger, func
from ..connection import Base

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

class TradeJournal(Base):
    __tablename__ = "trade_journal"
    
    id = Column(Integer, primary_key=True, index=True)
    tiket = Column(BigInteger, index=True)
    timestamp = Column(DateTime, index=True, default=func.now())
    event_type = Column(String, index=True) # ENTRY, SL_MODIFY, EXIT
    harga = Column(Float)
    alasan = Column(String) # Alasan AI / Top 3 Feature Contributions
    chart_snapshot = Column(String) # JSON 50 M1 candles
