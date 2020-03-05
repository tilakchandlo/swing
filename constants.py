"""
Global constants.
"""


# Instrument message fields
INSTRUMENTS = 'instruments'
INSTRUMENT_ID = 'instrumentID'
EXCHANGE_ID = 'exchangeID'
INSTRUMENT_SYMBOL = 'symbol'
INSTRUMENT_TRADING_HOURS = 'instrument_trading_hours'
UNIT_SIZE = 'unit_size'  # future's contract unit size
TICK_SIZE = 'tick_size'
MARGIN_TYPE = 'margin_type'
MARGIN_RATE = 'margin_rate'
OPEN_COMM_TYPE = 'open_comm_type'
OPEN_COMM_RATE = 'open_comm_rate'
CLOSE_COMM_TYPE = 'close_comm_type'
CLOSE_COMM_RATE = 'close_comm_rate'
CLOSE_TODAY_COMM_TYPE = 'close_today_comm_type'
CLOSE_TODAY_COMM_RATE = 'close_today_comm_rate'


# Tick message fields
ASK = 'ask'
BID = 'bid'
ASK_VOLUME = 'askVolume'
BID_VOLUME = 'bidVolume'
HIGH_LIMIT = 'highLimit'
LOW_LIMIT = 'lowLimit'


# Order and trade message fields
PRICE = 'price'
VOLUME = 'volume'
DIRECTION_LONG = 'long'
DIRECTION_SHORT = 'short'
DIRECTION = 'direction'
BUY = '0'
SELL = '1'
ORDER_ID = 'orderID'
TRADE_ID = 'tradeID'
QTY = 'qty'
TRADED_QTY = 'traded_qty'
TAG = 'tag'
ORDER_ACTION = 'order_action'
ORDER_STATUS = 'order_status'
ORDER_CREATE_DATE = 'order_create_date'
ORDER_EXPIRATION_DATE = 'order_expiration_date'
ORDER_ACCEPT_FLAG = 'order_accept_flag'
BUY_ORDERS = 'buy_orders'
SELL_ORDERS = 'sell_orders'
ORDER_IDS = 'order_ids'


# Order cancel type
CANCEL_TYPE = 'cancel_type'
CANCEL_ALL = 0
CANCEL_OPEN_ORDERS = 1
CANCEL_CLOSE_ORDERS = 2
CANCEL_STOPLOSS_ORDERS = 3
CANCEL_ORDERS = 4


# Order status
ORDER_ACCEPTED = 'order_status_accepted'
ORDER_OPEN = 'order_status_open'
ORDER_CLOSED = 'order_status_closed'
ORDER_CLOSED_ALIAS = 'order_status_executed'
ORDER_REJECTED = 'order_status_rejected'
ORDER_CANCELLED = 'order_status_cancelled'
ORDER_CANCEL_SUBMITTED = 'order_status_cancel_submitted'
ORDER_PARTIAL_CLOSED = 'order_status_partial_closed'
ORDER_NO_CANCEL = 'order_status_no_cancel'
ORDER_REPEAT_CANCEL = 'order_status_repeat_cancel'


# Broker data fields
PORTFOLIO_ID = 'portfolioID'
ACCOUNT_ID = 'accountID'


# Strategy debug log message strings
STRATEGY_CONFIG = "The strategy has been configured."
STRATEGY_OPEN = "The strategy opens a position. Params: [%s]"
STRATEGY_CLOSE = "The strategy closes a position. Params: [%s]"
STRATEGY_START = "The strategy is starting..."
STRATEGY_STOP = "The strategy is stopping..."
STRATEGY_SUSPEND = "The strategy is suspending..."
STRATEGY_RESUME = "The strategy is resuming..."
STRATEGY_STOPPED = "The strategy has stopped."
STRATEGY_SETTING_PARAMS = "The strategy parameters: [%s]"
ON_TICK = "onTick triggered with the event: [%s]"
ON_UPDATE_ORDER_STATUS = "Updating order status. Params [%s]"
ON_PROFIT_CHANGE = "EVENT_PROFITCHANGED triggered. Params: [%s]"
ON_BUY = "EVENT_BUY triggered. Params: [%s]"
ON_SELL = "EVENT_SELL triggered. Params: [%s]"


# Misc
COMPARED_FLOAT = 0.0000001
INVALID_VALUE = -1.0
TAG_DEFAULT_VALUE = ''
APP_ID = 'app_id'
