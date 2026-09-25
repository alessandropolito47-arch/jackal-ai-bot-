"""
STRATEGY CORE (MEGA) - VERSIONE 3.10 (allineata all'EA MT5 v3.10)
==================================================================
Aggiornamento del 25/09/2026 - filtri di entrata "F", scelti con il test
su 25 simboli / 8 anni eseguito con il motore di backtest corretto
(stop e target valutati sui minimi/massimi intraday, costi inclusi):

  - MFI (14) al posto del voto Volume: BUY se MFI > 50, SELL se MFI < 50
  - filtro SuperTrend (10, 3): BUY solo se rialzista, SELL solo se ribassista
  - filtro Ichimoku (9, 26, 52): BUY solo con chiusura sopra la nuvola,
    SELL solo sotto la nuvola
  - filtro anti-inseguimento: niente BUY se la chiusura e' oltre 3 ATR
    sopra la SMA20 (e simmetrico per i SELL)

Risultato del test (filtri F + parziale a +1R + trailing 2 ATR dopo la
parziale): +0,062 R netti per trade su 8 anni (significativo), +0,046 R
sugli ultimi 2 anni (positivo ma non ancora significativo).

Restano invariati: 8 voti con soglia 7 su 8 (EMA9/21, MACD, RSI, MFI,
Bollinger, CCI, Williams %R, ROC), filtro SMA100 + ADX >= 20, stop a
2 ATR, target a TAKE_PROFIT_ATR_MULTIPLIER x ATR.

I nuovi interruttori si leggono da config.py se presenti, altrimenti
valgono i predefiniti qui sotto (non serve modificare config.py):
  USE_MFI = True, USE_SUPERTREND = True, USE_ICHIMOKU = True,
  ANTI_CHASE_ATR = 3.0   (0 = filtro spento)

NOTA: la gestione dell'uscita (parziale a +1R, poi trailing a 2 ATR dal
massimo raggiunto) NON e' in questo file ma nel modulo che gestisce le
posizioni aperte, da aggiornare separatamente.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from mega_indicators import calculate_mega_indicators
from indicators import sma
import config

USE_MFI = getattr(config, "USE_MFI", True)
USE_SUPERTREND = getattr(config, "USE_SUPERTREND", True)
USE_ICHIMOKU = getattr(config, "USE_ICHIMOKU", True)
ANTI_CHASE_ATR = getattr(config, "ANTI_CHASE_ATR", 3.0)


@dataclass
class Decision:
    signal: str
    confirmations: int
    reasons: Dict[str, bool] = field(default_factory=dict)
    price: Optional[float] = None
    atr_value: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    volatility_scale: float = 1.0
    blocked_by: Optional[str] = None   # filtro che ha scartato un segnale (solo per il log)


# ----------------------------------------------------------------------
# Indicatori aggiuntivi v3.10 (calcolati sulle candele fino all'indice i)
# ----------------------------------------------------------------------
def _mfi(candles, i, period=14):
    """Money Flow Index sulla candela i. None se non calcolabile."""
    if i < period:
        return None
    pos, neg = 0.0, 0.0
    for k in range(i - period + 1, i + 1):
        tp = (candles[k][2] + candles[k][3] + candles[k][4]) / 3
        tp_prev = (candles[k - 1][2] + candles[k - 1][3] + candles[k - 1][4]) / 3
        flow = tp * candles[k][5]
        if tp > tp_prev:
            pos += flow
        elif tp < tp_prev:
            neg += flow
    if neg == 0:
        return 100.0
    return 100 - 100 / (1 + pos / neg)


def _supertrend_dir(candles, i, period=10, mult=3.0):
    """Direzione del SuperTrend sulla candela i: +1 rialzista, -1 ribassista, 0 n.d."""
    if i < period + 1:
        return 0
    atr = None
    tr_sum = 0.0
    fub = flb = None
    direction = 1
    for k in range(1, i + 1):
        h, l, c_prev = candles[k][2], candles[k][3], candles[k - 1][4]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        if k <= period:
            tr_sum += tr
            if k < period:
                continue
            atr = tr_sum / period            # prima media semplice, poi Wilder
        else:
            atr = (atr * (period - 1) + tr) / period
        hl2 = (h + l) / 2
        ub, lb = hl2 + mult * atr, hl2 - mult * atr
        if fub is None:
            fub, flb, direction = ub, lb, 1
            continue
        nfub = ub if (ub < fub or c_prev > fub) else fub
        nflb = lb if (lb > flb or c_prev < flb) else flb
        close = candles[k][4]
        if direction >= 0:
            direction = -1 if close < nflb else 1
        else:
            direction = 1 if close > nfub else -1
        fub, flb = nfub, nflb
    return direction


def _mid_hl(candles, end, period):
    """(massimo + minimo) / 2 delle 'period' candele che terminano all'indice end."""
    if end - period + 1 < 0:
        return None
    window = candles[end - period + 1: end + 1]
    return (max(c[2] for c in window) + min(c[3] for c in window)) / 2


def _ichimoku_pos(candles, i):
    """+1 chiusura sopra la nuvola, -1 sotto, 0 dentro o n.d.
    La nuvola 'attuale' e' quella calcolata 26 candele prima."""
    j = i - 26
    tenkan, kijun, span_b = _mid_hl(candles, j, 9), _mid_hl(candles, j, 26), _mid_hl(candles, j, 52)
    if tenkan is None or kijun is None or span_b is None:
        return 0
    span_a = (tenkan + kijun) / 2
    top, bot = max(span_a, span_b), min(span_a, span_b)
    close = candles[i][4]
    if close > top:
        return 1
    if close < bot:
        return -1
    return 0


# ----------------------------------------------------------------------
def evaluate(candles: List[list], index: Optional[int] = None) -> Decision:
    ind = calculate_mega_indicators(candles)
    i = index if index is not None else len(candles) - 1

    price = ind["close"][i]
    atr_value = ind["atr"][i]

    # Filtro di forza del trend (ADX)
    adx_value = ind["adx"][i]
    trend_strong_enough = adx_value is not None and adx_value >= config.ADX_MIN_STRENGTH

    # Filtro di tendenza di fondo (SMA100)
    trend_sma = sma(ind["close"], config.TREND_FILTER_PERIOD)
    trend_up = trend_sma[i] is not None and price > trend_sma[i]
    trend_down = trend_sma[i] is not None and price < trend_sma[i]

    reasons_buy = {}
    reasons_sell = {}

    # 1) EMA9 vs EMA21
    if ind["ema9"][i] is not None and ind["ema21"][i] is not None:
        reasons_buy["ema_9_21"] = ind["ema9"][i] > ind["ema21"][i]
        reasons_sell["ema_9_21"] = ind["ema9"][i] < ind["ema21"][i]

    # 2) MACD
    if ind["macd_line"][i] is not None and ind["macd_signal"][i] is not None:
        reasons_buy["macd"] = ind["macd_line"][i] > ind["macd_signal"][i]
        reasons_sell["macd"] = ind["macd_line"][i] < ind["macd_signal"][i]

    # 3) RSI (non ipercomprato/ipervenduto)
    if ind["rsi"][i] is not None:
        reasons_buy["rsi"] = ind["rsi"][i] < config.RSI_OVERBOUGHT
        reasons_sell["rsi"] = ind["rsi"][i] > config.RSI_OVERSOLD

    # 4) v3.10: MFI al posto del Volume (con USE_MFI = False torna il Volume)
    if USE_MFI:
        mfi_value = _mfi(candles, i)
        if mfi_value is not None:
            reasons_buy["mfi"] = mfi_value > 50
            reasons_sell["mfi"] = mfi_value < 50
    elif ind["volume"][i] is not None and ind["volume_sma"][i] is not None:
        vol_ok = ind["volume"][i] > ind["volume_sma"][i]
        reasons_buy["volume"] = vol_ok
        reasons_sell["volume"] = vol_ok

    # 5) Bollinger (rottura)
    if ind["bb_upper"][i] is not None and ind["bb_lower"][i] is not None:
        reasons_buy["bollinger"] = price > ind["bb_upper"][i]
        reasons_sell["bollinger"] = price < ind["bb_lower"][i]

    # 6) CCI
    if ind["cci"][i] is not None:
        reasons_buy["cci"] = ind["cci"][i] > 100
        reasons_sell["cci"] = ind["cci"][i] < -100

    # 7) Williams %R
    if ind["williams_r"][i] is not None:
        reasons_buy["williams_r"] = ind["williams_r"][i] > -50
        reasons_sell["williams_r"] = ind["williams_r"][i] < -50

    # 8) ROC
    if ind["roc"][i] is not None:
        reasons_buy["roc"] = ind["roc"][i] > 0
        reasons_sell["roc"] = ind["roc"][i] < 0

    buy_confirmations = sum(1 for v in reasons_buy.values() if v)
    sell_confirmations = sum(1 for v in reasons_sell.values() if v)

    volatility_scale = 1.0
    if config.VOLATILITY_SCALE_ENABLED and atr_value is not None:
        atr_series = ind["atr"]
        lookback_start = max(0, i - config.VOLATILITY_LOOKBACK)
        recent_atrs = [a for a in atr_series[lookback_start:i] if a is not None]
        if recent_atrs:
            avg_atr = sum(recent_atrs) / len(recent_atrs)
            if avg_atr > 0 and atr_value > avg_atr:
                volatility_scale = max(config.VOLATILITY_MIN_SCALE, avg_atr / atr_value)

    want_buy = (buy_confirmations >= config.MIN_INDICATORS_CONFIRMING and atr_value is not None
                and trend_up and trend_strong_enough)
    want_sell = (not want_buy and sell_confirmations >= config.MIN_INDICATORS_CONFIRMING
                 and atr_value is not None and trend_down and trend_strong_enough)

    # ---- v3.10: filtri di entrata (valutati solo se c'e' un segnale)
    blocked_by = None
    if want_buy or want_sell:
        side = 1 if want_buy else -1
        if USE_SUPERTREND and blocked_by is None:
            st = _supertrend_dir(candles, i)
            if st != side:
                blocked_by = "SuperTrend"
        if USE_ICHIMOKU and blocked_by is None:
            ic = _ichimoku_pos(candles, i)
            if ic != side:
                blocked_by = "Ichimoku"
        if ANTI_CHASE_ATR and blocked_by is None and atr_value:
            sma20 = ind["bb_mid"][i] if "bb_mid" in ind else sma(ind["close"], 20)[i]
            if sma20 is not None:
                dist = (price - sma20) / atr_value
                if side * dist > ANTI_CHASE_ATR:
                    blocked_by = f"anti-inseguimento ({dist:+.1f} ATR dalla SMA20)"

    if blocked_by is None and want_buy:
        stop = price - atr_value * config.ATR_STOP_MULTIPLIER
        target = price + atr_value * config.TAKE_PROFIT_ATR_MULTIPLIER
        return Decision("BUY", buy_confirmations, reasons_buy, price, atr_value, stop, target, volatility_scale)

    if blocked_by is None and want_sell:
        stop = price + atr_value * config.ATR_STOP_MULTIPLIER
        target = price - atr_value * config.TAKE_PROFIT_ATR_MULTIPLIER
        return Decision("SELL", sell_confirmations, reasons_sell, price, atr_value, stop, target, volatility_scale)

    return Decision("HOLD", max(buy_confirmations, sell_confirmations),
                    reasons_buy if buy_confirmations >= sell_confirmations else reasons_sell,
                    price, atr_value, blocked_by=blocked_by)
