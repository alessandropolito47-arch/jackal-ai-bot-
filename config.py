"""
CONFIG (MEGA) - Configurazione per la versione con tutti gli indicatori
============================================================================
"""

PAPER_TRADING = True

SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "DOGE/USDT",
    "DOT/USDT",
    "LINK/USDT",
    "LTC/USDT",
    "TRX/USDT",
    "ATOM/USDT",
    "UNI/USDT",
    "MATIC/USDT",
    "NEAR/USDT",
    "FIL/USDT",
    "ICP/USDT",
    "ETC/USDT",
    "XLM/USDT",
    "ALGO/USDT",
    "VET/USDT",
    "SAND/USDT",
    "MANA/USDT",
    "AAVE/USDT",
]

TIMEFRAMES = ["1d"]
DEFAULT_TIMEFRAME = "1d"

RISK_PER_TRADE_PCT = 0.05
MAX_CONCURRENT_POSITIONS = 3

ATR_STOP_MULTIPLIER = 2.0
TAKE_PROFIT_ATR_MULTIPLIER = 3.0

VOLATILITY_SCALE_ENABLED = True
VOLATILITY_LOOKBACK = 50
VOLATILITY_MIN_SCALE = 0.3

DRAWDOWN_CIRCUIT_BREAKER_PCT = 5.0

MIN_INDICATORS_CONFIRMING = 7
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

TREND_FILTER_PERIOD = 100

ADX_MIN_STRENGTH = 20

BACKTEST_STARTING_CAPITAL = 10_000.0
HISTORY_YEARS = 8

STATE_FILE = "positions_state_mega.json"
DECISION_LOG_FILE = "decision_log_mega.csv"
BACKTEST_REPORT_FILE = "mega_backtest_report.csv"
