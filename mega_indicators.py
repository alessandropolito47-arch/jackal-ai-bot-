"""
MEGA INDICATORS - Libreria estesa di indicatori tecnici
============================================================
Estende indicators.py (SMA, EMA, RSI, MACD, Bollinger, ATR, volume)
con altri indicatori classici, per costruire una strategia che vota
su un paniere molto piu' ampio di segnali.
"""

from indicators import sma, ema, rsi, macd, bollinger_bands, atr, volume_sma


def _highs(candles):
    return [c[2] for c in candles]


def _lows(candles):
    return [c[3] for c in candles]


def _closes(candles):
    return [c[4] for c in candles]


def _volumes(candles):
    return [c[5] for c in candles]


def stochastic(candles, k_period=14, d_period=3):
    highs, lows, closes = _highs(candles), _lows(candles), _closes(candles)
    k_values = [None] * len(candles)

    for i in range(k_period - 1, len(candles)):
        window_high = max(highs[i - k_period + 1: i + 1])
        window_low = min(lows[i - k_period + 1: i + 1])
        if window_high == window_low:
            k_values[i] = 50.0
        else:
            k_values[i] = 100 * (closes[i] - window_low) / (window_high - window_low)

    clean_k = [v for v in k_values if v is not None]
    d_partial = sma(clean_k, d_period)
    d_values = [None] * (len(k_values) - len(d_partial)) + d_partial

    return k_values, d_values


def adx(candles, period=14):
    highs, lows, closes = _highs(candles), _lows(candles), _closes(candles)
    n = len(candles)

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    def wilder_smooth(values, period):
        out = [None] * len(values)
        if len(values) <= period:
            return out
        first = sum(values[1:period + 1])
        out[period] = first
        for i in range(period + 1, len(values)):
            out[i] = out[i - 1] - (out[i - 1] / period) + values[i]
        return out

    smoothed_tr = wilder_smooth(tr, period)
    smoothed_plus_dm = wilder_smooth(plus_dm, period)
    smoothed_minus_dm = wilder_smooth(minus_dm, period)

    plus_di = [None] * n
    minus_di = [None] * n
    dx = [None] * n

    for i in range(n):
        if smoothed_tr[i] is not None and smoothed_tr[i] != 0:
            plus_di[i] = 100 * smoothed_plus_dm[i] / smoothed_tr[i]
            minus_di[i] = 100 * smoothed_minus_dm[i] / smoothed_tr[i]
            di_sum = plus_di[i] + minus_di[i]
            if di_sum != 0:
                dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum

    clean_dx_with_index = [(i, v) for i, v in enumerate(dx) if v is not None]
    adx_values = [None] * n
    if len(clean_dx_with_index) > period:
        start_idx = clean_dx_with_index[period - 1][0]
        first_adx = sum(v for _, v in clean_dx_with_index[:period]) / period
        adx_values[start_idx] = first_adx
        prev = first_adx
        prev_i = start_idx
        for idx, v in clean_dx_with_index[period:]:
            new_val = (prev * (period - 1) + v) / period
            adx_values[idx] = new_val
            prev = new_val

    return adx_values


def cci(candles, period=20):
    highs, lows, closes = _highs(candles), _lows(candles), _closes(candles)
    typical_prices = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(candles))]
    tp_sma = sma(typical_prices, period)

    out = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        if tp_sma[i] is None:
            continue
        window = typical_prices[i - period + 1: i + 1]
        mean_dev = sum(abs(tp - tp_sma[i]) for tp in window) / period
        if mean_dev != 0:
            out[i] = (typical_prices[i] - tp_sma[i]) / (0.015 * mean_dev)
    return out


def williams_r(candles, period=14):
    highs, lows, closes = _highs(candles), _lows(candles), _closes(candles)
    out = [None] * len(candles)
    for i in range(period - 1, len(candles)):
        window_high = max(highs[i - period + 1: i + 1])
        window_low = min(lows[i - period + 1: i + 1])
        if window_high != window_low:
            out[i] = -100 * (window_high - closes[i]) / (window_high - window_low)
    return out


def obv(candles):
    closes, volumes = _closes(candles), _volumes(candles)
    out = [0.0] * len(candles)
    for i in range(1, len(candles)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def roc(values, period=10):
    out = [None] * len(values)
    for i in range(period, len(values)):
        if values[i - period] != 0:
            out[i] = (values[i] - values[i - period]) / values[i - period] * 100
    return out


def calculate_mega_indicators(candles):
    closes = _closes(candles)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)
    macd_line, macd_signal = macd(closes)
    upper_bb, mid_bb, lower_bb = bollinger_bands(closes)
    stoch_k, stoch_d = stochastic(candles)

    return {
        "close": closes,
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi(closes),
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "bb_upper": upper_bb,
        "bb_mid": mid_bb,
        "bb_lower": lower_bb,
        "atr": atr(candles),
        "volume": _volumes(candles),
        "volume_sma": volume_sma(candles),
        "stoch_k": stoch_k,
        "stoch_d": stoch_d,
        "adx": adx(candles),
        "cci": cci(candles),
        "williams_r": williams_r(candles),
        "obv": obv(candles),
        "roc": roc(closes),
    }
