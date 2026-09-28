from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, func
from ..connection import Base

class ModelScorecard(Base):
    """
    Menyimpan riwayat evaluasi kuantitatif finansial (VectorBT OOS Fit & Proper Test)
    untuk setiap model AI yang dilatih atau dievaluasi secara manual.
    """
    __tablename__ = "model_scorecard"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    mode = Column(String(10), nullable=False, index=True) # 'normal' / 'runner'
    trained_at = Column(DateTime, nullable=False, default=func.now(), index=True)

    # Metrik finansial dari VectorBT
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0) # Win rate (%)
    profit_factor = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0) # Max drawdown (%)
    total_return = Column(Float, default=0.0) # Total return (%)

    # Status kelulusan
    passed = Column(Boolean, nullable=False, default=False, index=True)
    failure_reason = Column(Text, nullable=True)

    # Metadata & Horizon
    threshold_used = Column(Float, nullable=True)
    oos_start_date = Column(DateTime, nullable=True)
    oos_end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
