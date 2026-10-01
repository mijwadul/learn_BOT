from typing import Dict, Type
from .base_profile import BaseProfile
from .xauusd_profile import XAUUSDProfile
from .default_profile import DefaultProfile

_PROFILE_REGISTRY: Dict[str, Type[BaseProfile]] = {
    "XAUUSD": XAUUSDProfile,
    "GOLD": XAUUSDProfile,
    "XAU": XAUUSDProfile,
}

def get_profile(symbol: str = None) -> BaseProfile:
    """
    Factory function untuk memuat Quantitative Strategy Profile per instrumen.
    Mengembalikan instance profil spesifik instrumen (misal XAUUSDProfile)
    atau DefaultProfile jika belum terdaftar.
    """
    clean_sym = str(symbol or "DEFAULT").strip().upper()
    for key, profile_cls in _PROFILE_REGISTRY.items():
        if key in clean_sym:
            return profile_cls()
    return DefaultProfile()

__all__ = ["BaseProfile", "XAUUSDProfile", "DefaultProfile", "get_profile"]
