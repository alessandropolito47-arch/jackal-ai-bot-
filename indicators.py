"""
INDICATORS - Libreria di indicatori tecnici
==============================================
Calcolati senza dipendenze esterne oltre alle liste di candele
restituite da ccxt (formato OHLCV: [timestamp, open, high, low, close, volume]).

Ogni funzione restituisce una lista della stessa lunghezza delle
candele in ingresso, con None nei punti dove il valore non e'
ancora calcolabile (warm-up period).
"""


def _closes(candles):
    return [c[4] for c in candles]


def _highs(candles):
    return [c[2] for c in candles]


def _lows(candles):
    return [c[3] for c in candles]


def _volumes(candles):
    return [c[5] for c in candles]


def sma(values, period):
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1: i + 1]
        out[i] = sum(window) / period
    return out


def ema(values, period):
    out = [None] * len(values)
    multiplier = 2 / (period + 1)
    seed_index = period - 1
    if len(values) <= seed_index:
        return out
    seed = sum(values[:period]) / period
    out[seed_index] = seed
    for i in range(seed_index + 1, len(values)):
        out[i] = (values[i] - out[i - 1]) * multiplier + out[i - 1]
    return out


def rsi(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out

    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else None
        out[i + 1] = 100 - (100 / (1 + rs)) if rs is not None else 100
    return out


def macd(values, fast=12, slow=26, signal=9):
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    clean = [v for v in macd_line if v is not None]
    signal_partial = ema(clean, signal)
    signal_line = [None] * (len(macd_line) - len(signal_partial)) + signal_partial
    return macd_line, signal_line


def bollinger_bands(values, period=20, std_mult=2.0):
    mid = sma(values, period)
    upper = [None] * len(values)
    lower = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1: i + 1]
        mean = mid[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        upper[i] = mean + std_mult * std
        lower[i] = mean - std_mult * std
    return upper, mid, lower


def atr(candles, period=14):
    highs, lows, closes = _highs(candles), _lows(candles), _closes(candles)
    trs = [None]
    for i in range(1, len(candles)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    out = [None] * len(candles)
    valid_trs = [t for t in trs if t is not None]
    if len(valid_trs) < period:
        return out

    first_atr = sum(valid_trs[:period]) / period
    start_index = period
    out[start_index] = first_atr
    for i in range(start_index + 1, len(candles)):
        out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    return out


def volume_sma(candles, period=20):
    return sma(_volumes(candles), period)


def calculate_all_indicators(candles, ema_fast_period=9, ema_slow_period=21):
    closes = _closes(candles)
    ema_fast = ema(closes, ema_fast_period)
    ema_slow = ema(closes, ema_slow_period)
    macd_line, macd_signal = macd(closes)
    upper_bb, mid_bb, lower_bb = bollinger_bands(closes)

    return {
        "close": closes,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "rsi": rsi(closes),
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "bb_upper": upper_bb,
        "bb_mid": mid_bb,
        "bb_lower": lower_bb,
        "atr": atr(candles),
        "volume_sma": volume_sma(candles),
        "volume": _volumes(candles),
    }
