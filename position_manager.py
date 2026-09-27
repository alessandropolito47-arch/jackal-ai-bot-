"""
POSITION MANAGER - Gestione delle posizioni aperte (allineata all'EA MT5 v3.16)
==================================================================================
Usato sia dal controllo giornaliero (mega_paper_trading_github.py) sia dalla
sorveglianza intraday (intraday_monitor.py), cosi' le regole sono identiche.

Regole (test "trailing" con motore corretto: +0,062 R netti su 8 anni):
  1. Stop iniziale a 1R (= ATR_STOP_MULTIPLIER x ATR)
  2. A +1R: chiude META' posizione, stop della meta' restante a PAREGGIO
  3. Dopo la parziale lo stop SEGUE il prezzo a TRAILING_ATR x ATR dal
     massimo raggiunto (dal minimo per i SELL); non torna mai indietro
     e non scende mai sotto il pareggio
  4. Target finale a TAKE_PROFIT_ATR_MULTIPLIER x ATR (5 ATR = 2,5R)
Le posizioni gia' aperte con un target piu' vicino vengono allineate.
"""
from datetime import datetime

import config

PARTIAL_TP_R = getattr(config, "PARTIAL_TP_R", 1.0)
TRAILING_ATR = getattr(config, "TRAILING_ATR", 2.0)


def _side(position):
    return 1 if position["side"] == "BUY" else -1


def allinea_target(position):
    """Porta il target a TAKE_PROFIT_ATR_MULTIPLIER se quello attuale e' piu' vicino.
    Ritorna il nuovo target se modificato, altrimenti None."""
    r = position.get("initial_risk_distance") or 0
    if r <= 0:
        return None
    s = _side(position)
    entry = position["entry_price"]
    target = entry + s * r * config.TAKE_PROFIT_ATR_MULTIPLIER / config.ATR_STOP_MULTIPLIER
    if s * (target - position["take_profit_price"]) > abs(target) * 1e-9:
        position["take_profit_price"] = target
        return target
    return None


def aggiorna_estremo(position, prezzo):
    """Aggiorna il massimo (BUY) o minimo (SELL) raggiunto dal prezzo."""
    s = _side(position)
    e = position.get("extreme_price", position["entry_price"])
    position["extreme_price"] = max(e, prezzo) if s == 1 else min(e, prezzo)


def aggiorna_estremo_da_candele(position, candles):
    """Usa i massimi/minimi delle candele giornaliere CHIUSE dall'apertura
    (l'ultima candela, ancora in corso, viene esclusa)."""
    try:
        aperta = datetime.fromisoformat(position["opened_at"]).timestamp() * 1000
    except (KeyError, ValueError):
        return
    s = _side(position)
    for c in candles[:-1]:
        if c[0] + 86_400_000 <= aperta:      # candela terminata prima dell'apertura
            continue
        aggiorna_estremo(position, c[2] if s == 1 else c[3])


def aggiorna_trailing(position):
    """Dopo la parziale sposta lo stop a TRAILING_ATR x ATR dal massimo/minimo,
    mai indietro e mai oltre il pareggio. Ritorna il nuovo stop se spostato."""
    if not position.get("partial_taken"):
        return None
    r = position.get("initial_risk_distance") or 0
    if r <= 0:
        return None
    s = _side(position)
    entry = position["entry_price"]
    atr = r / config.ATR_STOP_MULTIPLIER
    e = position.get("extreme_price", entry)
    nuovo = e - s * TRAILING_ATR * atr
    nuovo = max(nuovo, entry) if s == 1 else min(nuovo, entry)
    if s * (nuovo - position["stop_price"]) > abs(nuovo) * 1e-9:
        position["stop_price"] = nuovo
        return nuovo
    return None


def check_position(position, current_price):
    """Decide cosa fare con una posizione al prezzo attuale.
    Ritorna None, {"action": "partial", ...} oppure {"action": "close", ...}."""
    s = _side(position)
    entry = position["entry_price"]
    stop = position["stop_price"]
    target = position["take_profit_price"]
    r = position["initial_risk_distance"]
    risk_amount = position["risk_amount"]
    if not r:
        return None

    hit_stop = (current_price <= stop) if s == 1 else (current_price >= stop)
    hit_target = (current_price >= target) if s == 1 else (current_price <= target)

    if not position.get("partial_taken", False):
        current_r = s * (current_price - entry) / r
        if hit_stop:
            return {"action": "close", "pnl": -risk_amount, "reason": "STOP-LOSS", "r_multiple": -1.0}
        if hit_target:
            r_mult = s * (target - entry) / r
            return {"action": "close", "pnl": risk_amount * r_mult, "reason": "TAKE-PROFIT", "r_multiple": r_mult}
        if current_r >= PARTIAL_TP_R:
            return {"action": "partial", "pnl": risk_amount * PARTIAL_TP_R * 0.5, "new_stop": entry}
        return None

    locked = position.get("partial_r_locked", 0.0)
    if hit_target:
        resto = 0.5 * s * (target - entry) / r
        return {"action": "close", "pnl": risk_amount * resto,
                "reason": "TAKE-PROFIT (meta' residua)", "r_multiple": locked + resto}
    if hit_stop:
        resto = 0.5 * s * (stop - entry) / r
        motivo = "TRAILING STOP (meta' residua)" if resto > 1e-9 else "PAREGGIO (dopo presa parziale)"
        return {"action": "close", "pnl": risk_amount * resto, "reason": motivo, "r_multiple": locked + resto}
    return None
