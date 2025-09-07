from __future__ import annotations
import re
from typing import Optional

_SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,20}$")

def validate_symbol(sym: Optional[str]) -> Optional[str]:
    if not sym: 
        return "symbol manquant"
    if not _SYMBOL_RE.match(sym):
        return "format de symbol invalide"
    return None

def validate_qty(qty) -> Optional[str]:
    try:
        q = float(qty)
        if q <= 0: 
            return "qty doit être > 0"
        return None
    except Exception:
        return "qty invalide"
