"""
STRATEGY CORE (MEGA) - VERSIONE OTTIMIZZATA
==================================================================
Aggiornamento del 22/09/2026: rimossi OBV, Stocastico e EMA 21/50 dal
voto, dopo verifica con ablation test completo + validazione
out-of-sample su 25 simboli/8 anni di storico giornaliero.

Risultato della validazione (dati alla base della decisione):
- In-sample (primi 6 anni): baseline +0.1597R vs senza-i-3 +0.2143R
- Out-of-sample (ultimi 2 anni, mai usati per la scoperta):
  baseline +0.1069R (IC95% include lo zero, non piu' significativo)
  vs senza-i-3 +0.1365R (IC95% +0.0163 a +0.2550, ancora significativo)

Restano 8 indicatori attivi: EMA9/21 (trend veloce), MACD, RSI,
Volume, Bollinger, CCI, Williams %R, ROC. Soglia di conferma invariata
a 7 (ora quindi 7 su 8, non piu' 7 su 11).

Nota metodologica onesta: aggiungere piu' indicatori NON garantisce
un vantaggio migliore - infatti qui abbiamo verificato con backtest
rigoroso che RIMUOVERNE alcuni migliora il risultato, non il contrario.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from mega_indicators import calculate_mega_indicators
from indicators import sma
import config


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


def evaluate(candles: List[list], index: Optional[int] = None) -> Decision:
    ind = calculate_mega_indicators(candles)
    i = index if index is not None else len(candles) - 1

    price = ind["close"][i]
    atr_value = ind["atr"][i]

    # Filtro di forza del trend: sotto questa soglia ADX, il mercato
    # e' considerato troppo laterale per operare.
    adx_value = ind["adx"][i]
    trend_strong_enough = adx_value is not None and adx_value >= config.ADX_MIN_STRENGTH

    # Filtro di tendenza di fondo
    trend_sma = sma(ind["close"], config.TREND_FILTER_PERIOD)
    trend_up = trend_sma[i] is not None and price > trend_sma[i]
    trend_down = trend_sma[i] is not None and price < trend_sma[i]

    reasons_buy = {}
    reasons_sell = {}

    # 1) Trend EMA veloce/lenta (EMA9 vs EMA21) - MANTENUTO
    if ind["ema9"][i] is not None and ind["ema21"][i] is not None:
        reasons_buy["ema_9_21"] = ind["ema9"][i] > ind["ema21"][i]
        reasons_sell["ema_9_21"] = ind["ema9"][i] < ind["ema21"][i]

    # EMA21 vs EMA50 - RIMOSSO (validato dal test di ablation/out-of-sample)

    # 2) MACD - MANTENUTO
    if ind["macd_line"][i] is not None and ind["macd_signal"][i] is not None:
        reasons_buy["macd"] = ind["macd_line"][i] > ind["macd_signal"][i]
        reasons_sell["macd"] = ind["macd_line"][i] < ind["macd_signal"][i]

    # 3) RSI (non ipercomprato/ipervenduto) - MANTENUTO
    if ind["rsi"][i] is not None:
        reasons_buy["rsi"] = ind["rsi"][i] < config.RSI_OVERBOUGHT
        reasons_sell["rsi"] = ind["rsi"][i] > config.RSI_OVERSOLD

    # 4) Volume sopra la sua media - MANTENUTO
    if ind["volume"][i] is not None and ind["volume_sma"][i] is not None:
        vol_ok = ind["volume"][i] > ind["volume_sma"][i]
        reasons_buy["volume"] = vol_ok
        reasons_sell["volume"] = vol_ok

    # 5) Posizione sulle Bollinger Bands - MANTENUTO
    if ind["bb_upper"][i] is not None and ind["bb_lower"][i] is not None:
        reasons_buy["bollinger"] = price > ind["bb_upper"][i]
        reasons_sell["bollinger"] = price < ind["bb_lower"][i]

    # Stocastico - RIMOSSO (validato dal test di ablation/out-of-sample)

    # 6) CCI - MANTENUTO
    if ind["cci"][i] is not None:
        reasons_buy["cci"] = ind["cci"][i] > 100
        reasons_sell["cci"] = ind["cci"][i] < -100

    # 7) Williams %R - MANTENUTO
    if ind["williams_r"][i] is not None:
        reasons_buy["williams_r"] = ind["williams_r"][i] > -50
        reasons_sell["williams_r"] = ind["williams_r"][i] < -50

    # OBV - RIMOSSO (validato dal test di ablation/out-of-sample)

    # 8) ROC (momentum di prezzo) - MANTENUTO
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

    if (buy_confirmations >= config.MIN_INDICATORS_CONFIRMING and atr_value is not None
            and trend_up and trend_strong_enough):
        stop = price - atr_value * config.ATR_STOP_MULTIPLIER
        target = price + atr_value * config.TAKE_PROFIT_ATR_MULTIPLIER
        return Decision("BUY", buy_confirmations, reasons_buy, price, atr_value, stop, target, volatility_scale)

    if (sell_confirmations >= config.MIN_INDICATORS_CONFIRMING and atr_value is not None
            and trend_down and trend_strong_enough):
        stop = price + atr_value * config.ATR_STOP_MULTIPLIER
        target = price - atr_value * config.TAKE_PROFIT_ATR_MULTIPLIER
        return Decision("SELL", sell_confirmations, reasons_sell, price, atr_value, stop, target, volatility_scale)

    return Decision("HOLD", max(buy_confirmations, sell_confirmations),
                     reasons_buy if buy_confirmations >= sell_confirmations else reasons_sell,
                     price, atr_value)
