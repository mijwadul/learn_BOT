from sqlalchemy import Column, Integer, String, Float, DateTime, func
from ..connection import Base

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
