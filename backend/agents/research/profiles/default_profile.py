from .base_profile import BaseProfile


class DefaultProfile(BaseProfile):
    """
    Profil Kuantitatif Standar / Fallback untuk instrumen selain XAUUSD
    (BTCUSD, USOIL, GBPUSD, dll.) sebelum dilakukan spesialisasi mandiri.
    """
    symbol: str = "DEFAULT"
