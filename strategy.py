"""
Definition of base strategy and related types.
"""


from abc import ABC
from datetime import datetime
from threading import Thread
from constants import *
from utils import get_number_of_decimal, if_market_open
from events import EVENT_MARKETDATA, EVENT_BUY, EVENT_SELL, EVENT_CANCEL, EVENT_TRADE, EVENT_STATUS, EVENT_PROFIT_CHANGED
from events import StrategyEvent, EventEngine


# Constants
INIT = "INIT"
REQ = "REQ"
SPLIT = "SPLIT"


# --- Exceptions ---
class InvalidMarginFee(Exception):
    """
    Exception raised if Strategy.instru_margin_comm_rate is empty when receiving a MarketData event.
    """
    pass


class InvalidTickSize(Exception):
    """
    Exception raised if current or cached tick size is not numeric when receiving a MarketData event.
    """
    pass


class InvalidContractUnit(Exception):
    """
    Exception raised if current or cached contract unit is not numeric when receiving a MarketData event.
    """
    pass


# --- Data Classes ---
class Contract:
    """
    Contract specs and its latest market status.
    """
    __slots__ = ("symbol", "instrument_id", "tick", "unit", "margin_fee", "trading_hours", "decimal", "last", "bid",
                 "ask", "bid_volume", "ask_volume", "low_limit", "high_limit")

    def __init__(self, symbol=None, instrument_id=None, tick=None, unit=None, margin_fee=None, trading_hours=None):
        # Constant contract specs
        self.symbol = symbol
        self.instrument_id = instrument_id
        self.trading_hours = trading_hours

        # Variable contract specs
        self.tick = tick
        self.unit = unit
        self.margin_fee = {  # margin and commission fee information
            DIRECTION_LONG: {},
            DIRECTION_SHORT: {}
        } if margin_fee is None else margin_fee
        self.decimal = None

        # Market status from exchange: prices, volumes, depths, volatility, etc.
        self.low_limit = None
        self.high_limit = None
        self.last = None
        self.bid = None
        self.ask = None
        self.bid_volume = None
        self.ask_volume = None

    def reset_market_status(self):
        """
        Reset the contract's market status.
        """
        self.tick = None
        self.unit = None
        self.margin_fee = {DIRECTION_LONG: {}, DIRECTION_SHORT: {}}
        self.decimal = None
        self.low_limit = None
        self.high_limit = None
        self.last = None
        self.bid = None
        self.ask = None
        self.bid_volume = None
        self.ask_volume = None


class OrderRecord:
    """
    All information of an order.
    """
    __slots__ = ("contract", "order_id", "create_time", "expiration_time", "buy_sell", "long_short", "price", "qty",
                 "tag", "status", "filled_qty", "filled_price", "trades")

    def __init__(self, contract, order_id, create_time, expiration_time, buy_sell, long_short, price, qty, tag):
        """
        :param contract: Contract
        :param order_id: int
        :param create_time: str
        :param expiration_time: str
        :param buy_sell: int. 0: buy, 1: sell
        :param long_short: int. 0: long, 1: short
        :param price: float
        :param qty: int
        :param tag: str
        """
        self.contract = contract
        self.order_id = order_id
        self.create_time = create_time
        self.expiration_time = expiration_time
        self.buy_sell = buy_sell  # 0/1
        self.long_short = long_short  # 0/1
        self.price = price
        self.qty = qty
        self.tag = tag
        self.status = ORDER_OPEN
        self.filled_qty = 0
        self.filled_price = 0.0
        self.trades = []  # list of str, trade ids.

    def __repr__(self):
        return (
            "Order {}: {} {} price={} qty={} tag={} status={} filled_qty={} filled_price={} trades={} create_time={}".
            format(self.order_id, ('buy', 'sell')[self.buy_sell], ('long', 'short')[self.long_short], self.price,
                   self.qty, self.tag, self.status, self.filled_qty, self.filled_price, self.trades, self.create_time))


class TradeRecord:
    """
    All information of a trade.
    """
    __slots__ = ("trade_id", "order_id", "price", "qty", "create_time")

    def __init__(self, trade_id, order_id, price, qty, create_time):
        """
        :param trade_id: int
        :param order_id: int
        :param price: float
        :param qty: int
        :param create_time: str
        """
        self.trade_id = trade_id
        self.order_id = order_id
        self.price = price
        self.qty = qty
        self.create_time = create_time

    def __repr__(self):
        return ("Trade {} for Order {}: price={} qty={} time={}".format(self.trade_id, self.order_id, self.price,
                                                                        self.qty, self.create_time))



class MetaStrategy(ABC):
    def __init__(self):
        self.event_engine = EventEngine()


class Strategy(MetaStrategy):
    """
    Base Strategy class with attributes and methods common to all strategies.
    """

    def __init__(self):
        Strategy.__init__(self)

        # Auxiliary attributes
        self.contract = Contract()  # The contract's latest specs and market status
        self.order_dict = {}  # orders look-up table by order_id
        self.trade_dict = {}  # trades look-up table by trade_id
        self._position_qty = [0, 0]  # Position quantity for long/short
        self._cma_price = [0.0, 0.0]  # Cumulative moving average price of position cost
        self._principal = 0.00  # principal cash
        self._gain = 0.00  # current profit
        self._nlv = 0.0  # net liquidation value

        # Thread for querying the margin and commission rate
        self.__margin_commission_thread = None
        self.__cancel_pending_orders_thread = None

    # --- API functions to be overridden by user strategies --- #
    def strategy_config_params(self, strategy_params):
        """
        Config strategy specific parameters.
        :param strategy_params: dict. Strategy specific parameters set by user. If None, default all params.
        """
        pass

    def strategy_config_on_start(self):
        """
        Resets and configs of strategy attributes on start.
        """
        pass

    def strategy_config_on_stop(self):
        """
        Clean up actions of strategy attributes on stop.
        """
        pass

    def strategy_rules_on_tick(self, event):
        """
        Run strategy rules after standard on tick rules.
        :param event: StrategyEvent of EVENT_MARKETDATA.
        :return: None
        """
        pass

    def strategy_rules_on_buy_success(self, order_ids):
        """
        Run strategy rules when buy action is successful.
        :param order_ids: List of successfully submitted order ids.
        """
        pass

    def strategy_rules_on_buy_fail(self, order_tag):
        """
        Run strategy rules when buy action fails.
        :param order_tag: TAG field string sent with the failed order request.
        """
        pass

    def strategy_rules_on_sell_success(self, order_ids):
        """
        Run strategy rules when buy action is successful.
        :param order_ids: List of successfully submitted order ids.
        """
        pass

    def strategy_rules_on_sell_fail(self, order_tag):
        """
        Run strategy rules when sell action fails.
        :param order_tag: TAG field string sent with the failed order request.        
        """
        pass

    def strategy_rules_on_cancel(self, event):
        """
        Run strategy rules after standard cancel operation.
        :param event: StrategyEvent of EVENT_CANCEL.
        :return: None
        """
        pass

    def strategy_rules_on_trade_update(self, order_id, trade_id):
        """
        Run strategy rules after standard trade update.
        :param order_id: int. Order id for the trade.
        :param trade_id: int. Trade id for the trade.
        :return: None
        """
        pass

    def strategy_rules_on_order_status(self, order_id, order_status):
        """
        Run strategy rules after standard order status update.
        :param order_id: int. Order id.
        :param order_status: str. Order status.
        :return: None
        """
        pass

    # --- Strategy configuration and control --- #

    def _register_event_handlers(self):
        """
        Register event handlers with event engine.
        :return: None
        """
        self.event_engine.register(EVENT_MARKETDATA, self.on_tick)
        self.event_engine.register(EVENT_BUY, self.on_buy)
        self.event_engine.register(EVENT_SELL, self.on_sell)
        self.event_engine.register(EVENT_CANCEL, self.on_cancel)
        self.event_engine.register(EVENT_TRADE, self.on_trade_update)
        self.event_engine.register(EVENT_STATUS, self.on_order_status)
        self.event_engine.register(EVENT_PROFIT_CHANGED, self.on_profit_change)

    def _unregister_event_handlers(self):
        """
        Deregister event handlers from event engine.
        :return: None
        """
        self.event_engine.unregister(EVENT_MARKETDATA, self.on_tick)
        self.event_engine.unregister(EVENT_BUY, self.on_buy)
        self.event_engine.unregister(EVENT_SELL, self.on_sell)
        self.event_engine.unregister(EVENT_CANCEL, self.on_cancel)
        self.event_engine.unregister(EVENT_TRADE, self.on_trade_update)
        self.event_engine.unregister(EVENT_STATUS, self.on_order_status)
        self.event_engine.unregister(EVENT_PROFIT_CHANGED, self.on_profit_change)

    def _reset_ext_base_strategy(self):
        self.order_dict = {}
        self.trade_dict = {}
        self.contract.reset_market_status()
        self._position_qty = [0, 0]
        self._cma_price = [0.0, 0.0]
        self._principal = float(self.portfolio_obj.get_principal_by_this_running(self.account_id))
        self._gain = 0.00

    def config(self, strategy_setting, cash_check=True):
        """
        Update strategy parameters by user settings.
        :param strategy_setting: strategy settings set by user
        :param cash_check: whether or not to check cash in the configuration
        :return: None
        """
        if not Strategy.config(self, strategy_setting, cash_check):
            self.open_times = ""
            self.contract.instrument_id = None
            self.contract.symbol = None
            self.strategy_config_params(None)
            return

        instr = strategy_setting[INSTRUMENTS][0]
        self.open_times = instr.get(INSTRUMENT_TRADING_HOURS, self.open_times)
        self.contract.instrument_id = instr[INSTRUMENT_ID]
        self.contract.symbol = instr[INSTRUMENT_SYMBOL]
        self.contract.trading_hours = instr.get(INSTRUMENT_TRADING_HOURS, self.open_times)
        self.strategy_config_params(strategy_setting[self.contract.symbol])

        settings_dict = {
            INSTRUMENT_TRADING_HOURS: self.open_times,
            INSTRUMENT_ID: self.contract.instrument_id,
            INSTRUMENT_SYMBOL: self.contract.symbol
        }
        settings_dict.update(strategy_setting[self.contract.symbol])
        self.logger.debug(STRATEGY_SETTING_PARAMS, settings_dict)

    def start(self):
        """
        Start running strategy.
        :return: None
        """
        self.logger.info(STRATEGY_START)

        self.reset_properties_for_restart()
        self._reset_ext_base_strategy()

        self.strategy_config_on_start()  # API

        self.__cancel_pending_orders_thread = Thread(target=self.cancel_untraded_orders)
        self.__cancel_pending_orders_thread.start()
        self.__margin_commission_thread = Thread(
            target=self.query_margin_commission_rate, args=([
                self.contract.symbol,
            ],))
        self.__margin_commission_thread.start()

        self._register_event_handlers()
        self.event_engine.start()

    def stop(self):
        """
        Stop running strategy.
        :return: None
        """
        self.logger.info(STRATEGY_STOP)
        self.thread_lock.acquire()
        self.active = False
        self.error_code = None
        self.thread_lock.release()

        self.thread_cond.acquire()
        self.thread_cond.notifyAll()  # wake up margin commission thread
        self.thread_cond.release()
        if self.__cancel_pending_orders_thread.isAlive():
            self.__cancel_pending_orders_thread.join()
        if self.__margin_commission_thread.isAlive():
            self.__margin_commission_thread.join()

        self._unregister_event_handlers()
        self.event_engine.stop()

        self.strategy_config_on_stop()  # API

        self.portfolio_obj.clear_all_accounts()
        self.cancel_before_stop()  # cancel all pending orders
        self.logger.info(STRATEGY_STOPPED)

    # --- Event handlers with standard processing --- #

    def on_profit_change(self, event):
        """
        EVENT_PROFIT_CHANGED handler.
        :param event: StrategyEvent of EVENT_PROFIT_CHANGED
        :return: None
        """
        Strategy.profit_change(self, event)

    def on_buy(self, event):
        """
        EVENT_BUY handler.
        :param event: StrategyEvent of EVENT_BUY
        :return: None
        """
        # Check if order price is out of exchange limits
        price_valid = self.contract.low_limit <= event.even_param[PRICE] <= self.contract.high_limit
        if not price_valid:
            self.strategy_rules_on_buy_fail(event.even_param[TAG])
            self.logger.error(
                "EVENT_BUY: Price out of limits. Direction={} TAG={} Qty={} Price={} Limits = {}, {}".format(
                    event.even_param[DIRECTION], event.even_param[TAG], event.even_param[QTY],
                    event.even_param[PRICE], self.contract.low_limit, self.contract.high_limit))
            return

        # Reduce order qty if not enough cash
        order_qty = event.even_param[QTY]
        remaining_cash = self.portfolio_obj.get_remaining_cash(self.account_id)
        while event.even_param[QTY] > 0 and (
                remaining_cash < self.calculate_margin(event) + self.calculate_open_commission_with_event(event)):
            event.even_param[QTY] -= 1
        if event.even_param[QTY] <= 0:  # Not enough cash to buy any
            event.even_param[QTY] = order_qty

        # Execute buy action
        buy_result = Strategy.buy_action(self, event)

        # Process buy result depending on buy action success/fail
        if buy_result[ORDER_ACCEPT_FLAG]:
            new_order_ids = self._save_orders_on_buy_sell(buy_result, event.even_param[TAG])
            self.strategy_rules_on_buy_success(new_order_ids)
        else:
            self.strategy_rules_on_buy_fail(event.even_param[TAG])

        # Update profit and cash
        self._update_profit(instantly=True)

    def on_sell(self, event):
        """
        EVENT_SELL handler.
        :param event: StrategyEvent of EVENT_SELL
        :return: None
        """
        # Check if order price is out of range exchange limits
        price_valid = self.contract.low_limit <= event.even_param[PRICE] <= self.contract.high_limit
        if not price_valid:
            self.strategy_rules_on_sell_fail(event.even_param[TAG])
            self.logger.error(
                "EVENT_Sell: Price out of limits. Direction={} TAG={} Qty={} Price={} Limits = {}, {}".format(
                    event.even_param[DIRECTION], event.even_param[TAG], event.even_param[QTY],
                    event.even_param[PRICE], self.contract.low_limit, self.contract.high_limit))
            return

        # Not enough virtual position to sell
        position_available_to_sell = self.portfolio_obj.get_traded_qty(
            self.account_id, self.contract.instrument_id, event.even_param[DIRECTION], real_time=False)
        if event.even_param[QTY] > position_available_to_sell:
            self.strategy_rules_on_sell_fail(event.even_param[TAG])
            self.logger.error(
                "EVENT_SELL: Not enough position to sell. Direction={} TAG={} Qty={} Price={} Position={}".format(
                    event.even_param[DIRECTION], event.even_param[TAG], event.even_param[QTY],
                    event.even_param[PRICE], position_available_to_sell))
            return

        # Execute sell action
        sell_result = Strategy.sell_action(self, event)

        # Process sell result depending on sell action success/fail
        if sell_result[ORDER_ACCEPT_FLAG]:
            new_order_ids = self._save_orders_on_buy_sell(sell_result, event.even_param[TAG])
            self.strategy_rules_on_sell_success(new_order_ids)
        else:
            self.strategy_rules_on_sell_fail(event.even_param[TAG])

        # Update profit and cash
        self._update_profit(instantly=True)

    def on_cancel(self, event):
        """
        EVENT_CANCEL handler.
        :param event: StrategyEvent of EVENT_CANCEL
        :return: None
        """
        Strategy.cancel_action(self, event)
        self.strategy_rules_on_cancel(event)

    def on_tick(self, event):
        """
        EVENT_MARKETDATA handler.
        :param event: StrategyEvent of EVENT_MARKETDATA
        :return: None
        """
        # Filter symbol
        if event.even_param[INSTRUMENT_SYMBOL] != self.contract.symbol:
            return

        # Check app active status, trading hours, margin/commission.
        try:
            self.thread_lock.acquire()
            if not self.active or self.suspend:
                return
            if not if_market_open(self.contract.trading_hours):
                return
            self._check_margin_fee()  # raise InvalidMarginFee if no margin fee information
        except InvalidMarginFee:
            return
        finally:
            if self.thread_lock.locked():
                self.thread_lock.release()

        # Update market status
        try:
            self._update_contract_market(event)
        except (InvalidContractUnit, InvalidTickSize):
            return False

        # Update portfolio
        self._update_profit(instantly=True)
        self._gain = self.portfolio_obj.get_gain_by_this_running(self.account_id)
        self._nlv = self._principal + self._gain

        # Log
        self.logger.info(ON_TICK, event.even_param)

        # Strategy rules
        self.strategy_rules_on_tick(event)

    def on_trade_update(self, event):
        """
        EVENT_TRADE handler.
        :param event: StrategyEvent of EVENT_TRADE.
        :return: None
        """
        # Standard update
        if not Strategy.trade_record_update(self, event):
            return

        # Extended update
        try:
            trade_id = int(event.even_param[TRADE_ID])
            order_id = int(event.even_param[ORDER_ID])
            price = float(event.even_param[PRICE])
            qty = abs(int(event.even_param[QTY]))
        except KeyError as e:
            self.logger.error("Event key error when updating trade: \n" + str(e))
            return None
        create_time = event.even_param[ORDER_CREATE_DATE]
        trade_record = TradeRecord(trade_id, order_id, price, qty, create_time)
        self.trade_dict[trade_id] = trade_record
        order_record = self.order_dict[order_id]
        order_record.filled_price = (order_record.filled_price * order_record.filled_qty + price * qty) / (
            order_record.filled_qty + qty)
        order_record.filled_qty += qty
        order_record.trades.append(trade_id)

        # Update position
        self._update_position_avg_price_on_trade(event)

        # Strategy rules
        self.strategy_rules_on_trade_update(order_id, trade_id)

    def on_order_status(self, event):
        """
        EVENT_STATUS handler.
        :param event: StrategyEvent of EVENT_STATUS.
        """
        # Standard update
        try:
            self.thread_lock.acquire()  # thread_lock acquiring to access portfolio_obj

            # Filter and parse event data
            order_id = event.even_param[ORDER_ID]
            if order_id not in self.portfolio_obj.query_all_order_ids():
                return
            self.logger.debug(ON_UPDATE_ORDER_STATUS, self.portfolio_id, event.even_param)
            order_status = event.even_param[ORDER_STATUS]
            self.logger.debug("Event_Status: Order ID = {}  Status = {}".format(order_id, order_status))
            if order_status not in (ORDER_CLOSED_ALIAS, ORDER_REJECTED, ORDER_CANCELLED, ORDER_REPEAT_CANCEL):
                return
            if order_status == ORDER_CLOSED_ALIAS:
                order_status = ORDER_CLOSED
            Strategy.order_status_update(self, {ORDER_ID: order_id, ORDER_STATUS: order_status})
            self.portfolio_obj.is_reset_for_accounts()

        except Exception:
            self.logger.error(ON_UPDATE_ORDER_STATUS, self.portfolio_id, event.even_param, exc_info=True)
            return False
        finally:
            if self.thread_lock.locked():
                self.thread_lock.release()

        # Extended update
        try:
            order_record = self.order_dict[order_id]
        except KeyError as e:
            self.logger.error("order_dict key error when updating order status: \n" + str(e))
            return

        if order_status in (ORDER_CLOSED, ORDER_REJECTED, ORDER_CANCELLED, ORDER_REPEAT_CANCEL):
            for trade_id in order_record.trades:
                try:
                    self.trade_dict.pop(trade_id)  # Remove all trades of the order in the trade dictionary
                except KeyError as e:
                    self.logger.error("trade_dict key error when removing order trades: \n" + str(e))
                    continue
            self.order_dict.pop(order_id)  # Remove the OrderRecord object in order dictionary
        else:  # Order not finished yet. Update status only.
            self.order_dict[order_id].status = order_status

        # Strategy rules
        self.strategy_rules_on_order_status(order_id, order_status)

    # --- Utilities for market status, account, position, order and trades management --- #

    def _update_profit(self, instantly=True):
        """
        Recalculate portfolio profit based on the current price.
        :param instantly: bool. Whether call base class method directly, or just append to event queue.
        :return: None
        """
        profit_para = {
            PORTFOLIO_ID: self.portfolio_id,
            ACCOUNT_ID: self.account_id,
            INSTRUMENT_ID: self.contract.instrument_id,
            PRICE: self.contract.last,
        }
        self.logger.debug(ON_PROFIT_CHANGE, profit_para)
        profit_event = StrategyEvent(EVENT_PROFIT_CHANGED, profit_para)
        if instantly:
            Strategy.profit_change(self, profit_event)
        else:
            self.event_engine.put(profit_event)

    def _check_margin_fee(self):
        """
        Check and update margin requirements and commission fee.
        *** Strategy thread_lock acquiring needed to call this method. ***
        :return: None
        """
        if len(self.instru_margin_comm_rate) == 0:
            raise InvalidMarginFee
        self.contract.margin_fee = {
            d: self.query_margin_rate(d, self.contract.symbol)
            for d in (DIRECTION_LONG, DIRECTION_SHORT)
        }

    def _update_contract_market(self, event):
        """
        Update strategy-wide market status variables from MarketData event.
        :param event: MarketData event
        :return: success flag (bool)
        """
        # Update contract unit and price tick
        if self.cache_flag:
            if event.even_param[UNIT_SIZE] != INVALID_VALUE:
                self.instru_unit_size[self.contract.symbol] = event.even_param[UNIT_SIZE]
            if event.even_param[TICK_SIZE] != INVALID_VALUE:
                self.instru_price_tick[self.contract.symbol] = event.even_param[TICK_SIZE]
                self.cache_flag = False
        self.contract.unit = self.instru_unit_size[self.contract.symbol] \
            if (event.even_param[UNIT_SIZE] - INVALID_VALUE < COMPARED_FLOAT) else event.even_param[UNIT_SIZE]
        self.contract.tick = self.instru_price_tick[self.contract.symbol] \
            if event.even_param[TICK_SIZE] - INVALID_VALUE < COMPARED_FLOAT else event.even_param[TICK_SIZE]
        if not isinstance(self.contract.unit, (int, float)):
            raise InvalidContractUnit
        if not isinstance(self.contract.tick, (int, float)):
            raise InvalidTickSize
        self.contract.decimal = get_number_of_decimal(self.contract.tick)

        # Update prices and volumes
        fields_map = {
            LOW_LIMIT: 'low_limit',
            HIGH_LIMIT: 'high_limit',
            PRICE: 'last',
            BID: 'bid',
            ASK: 'ask',
            BID_VOLUME: 'bid_volume',
            ASK_VOLUME: 'ask_volume'
        }
        for field, attr_name in fields_map.items():
            field_value = None
            try:
                if not isinstance(event.even_param[field], (int, float)) or event.even_param[field] < 0:
                    raise TypeError
                if field in (BID_VOLUME, ASK_VOLUME):
                    field_value = int(round(event.even_param[field]))
                else:
                    field_value = round(
                        round(event.even_param[field] / float(self.contract.tick)) * self.contract.tick,
                        self.contract.decimal)
                setattr(self.contract, attr_name, field_value)
            except Exception:  # TypeError or KeyError
                self.logger.debug("Market data exception: field = {} attr = {} val = {}".format(
                    field, attr_name, field_value))
                pass

    def _update_position_avg_price_on_trade(self, event):
        """
        Update position quantity and calculate average price when receiving EVENT_TRADE.
        Moving average price of current position is only updated on a buy trade, and does not change on a sell trade.
        Long/short average prices are updated separately.
        :param event: StrategyEvent of EVENT_TRADE
        :return: None
        """
        try:
            order_id = event.even_param[ORDER_ID]
            trade_action = self.order_dict[order_id].buy_sell  # 0: buy, 1: sell
            trade_direction = self.order_dict[order_id].long_short  # 0: long, 1: short
            trade_price = event.even_param[PRICE]
            trade_qty = event.even_param[QTY]
        except KeyError as e:
            self.logger.error("Event key error when updating avg price: \n" + str(e))
            return
        update_position_avg_price(self._position_qty, self._cma_price, trade_action, trade_direction, trade_price,
                                  trade_qty)
        self.logger.debug("Position avg price updated: trade_direction = {} new cma = {} new qty = {}".format(
            trade_direction, self._cma_price, self._position_qty))

    def _save_orders_on_buy_sell(self, buy_sell_result, tag=TAG_DEFAULT_VALUE):
        """
        When buy/sell succeeds, save a new OrderRecord object to order dictionary and order id to long/short order list.
        :param buy_sell_result: Successful buy/sell result dictionary.
        :return: list of successfully submitted order ids.
        """
        new_order_ids = []
        for order in buy_sell_result.get(BUY_ORDERS, []) + buy_sell_result.get(SELL_ORDERS, []):
            # Create order record object
            try:
                order_id = int(order[ORDER_ID])
                buy_sell = {BUY: 0, SELL: 1}.get(order[ORDER_ACTION], None)
                long_short = {DIRECTION_LONG: 0, DIRECTION_SHORT: 1}.get(order[DIRECTION], None)
                price = float(order[PRICE])
                qty = abs(int(order[QTY]))
            except KeyError:
                continue
            create_time = order.get(ORDER_CREATE_DATE, None)
            expiration_time = order.get(ORDER_EXPIRATION_DATE, None)
            order_record = OrderRecord(self.contract, order_id, create_time, expiration_time, buy_sell, long_short,
                                       price, qty, tag)

            # Add order record object to order dictionary
            self.order_dict[order_id] = order_record
            new_order_ids.append(order_id)
        return new_order_ids

    # --- Utilities for executing strategy --- #

    def send_limit_order(self, order_params_list):
        """
        Repack order_params with other params and put buy/sell events in engine.
        :param order_params_list: List of order params dictionaries returned from calc_order_params().
        :return: None
        """
        for order_params in order_params_list:
            if order_params['qty'] > 0:
                order_para = {
                    ACCOUNT_ID:
                    self.account_id,
                    PORTFOLIO_ID:
                    self.portfolio_id,
                    INSTRUMENT_ID:
                    self.contract.instrument_id,
                    INSTRUMENT_SYMBOL:
                    self.contract.symbol,
                    DIRECTION:
                    order_params['direction'],
                    PRICE:
                    round(
                        round(float(order_params['price']) / self.contract.tick) * self.contract.tick,
                        self.contract.decimal),
                    QTY:
                    order_params['qty'],
                    TAG:
                    TAG_DEFAULT_VALUE if order_params['tag'] is None else order_params['tag'],
                    ORDER_ACTION:
                    order_params['action'],
                    UNIT_SIZE:
                    self.contract.unit,
                    MARGIN_TYPE:
                    self.contract.margin_fee[order_params['direction']][MARGIN_TYPE],
                    MARGIN_RATE:
                    self.contract.margin_fee[order_params['direction']][MARGIN_RATE],
                    OPEN_COMM_TYPE:
                    self.contract.margin_fee[order_params['direction']][OPEN_COMM_TYPE],
                    OPEN_COMM_RATE:
                    self.contract.margin_fee[order_params['direction']][OPEN_COMM_RATE],
                    CLOSE_COMM_TYPE:
                    self.contract.margin_fee[order_params['direction']][CLOSE_COMM_TYPE],
                    CLOSE_COMM_RATE:
                    self.contract.margin_fee[order_params['direction']][CLOSE_COMM_RATE],
                    CLOSE_TODAY_COMM_RATE:
                    self.contract.margin_fee[order_params['direction']][CLOSE_TODAY_COMM_RATE],
                    APP_ID:
                    self.app_id
                }
                order_event = StrategyEvent({
                    BUY: EVENT_BUY,
                    SELL: EVENT_SELL
                }[order_params['action']], order_para)
                self.event_engine.put(order_event)
                self.logger.debug({BUY: ON_BUY, SELL: ON_SELL}[order_params['action']], order_para)

    def cancel_all_orders(self):
        """
        Cancel all pending orders.
        :return: None
        """
        self.event_engine.put(StrategyEvent(EVENT_CANCEL, {CANCEL_TYPE: CANCEL_ALL}))
        self.logger.debug("The event[EVENT_CANCEL] (CANCEL_ALL) is being triggered.")

    def cancel_orders(self, order_ids):
        """
        Cancel a bunch of pending orders.
        :param order_ids: iterable. Order id strings.
        :return: None.
        """
        self.event_engine.put(StrategyEvent(EVENT_CANCEL, {CANCEL_TYPE: CANCEL_ORDERS, ORDER_IDS: order_ids}))
        self.logger.debug("The event[EVENT_CANCEL] is being triggered for orders: %s." % order_ids)

    def run_adaptive_order(self, adaptive_order_obj):
        order_status, order_params = adaptive_order_obj.on_tick()
        order_finished = True if order_status in (ORDER_CLOSED, ORDER_CANCELLED) else False
        if order_status == ORDER_OPEN:
            if order_params['action'] == 'CANCEL':
                self.cancel_orders([order_params['order_id']])
            else:
                self.send_limit_order([order_params])
        return order_finished




# --- Static Utilities ---

def calc_order_params(buy_or_sell,
                      direction,
                      order_price,
                      order_qty,
                      order_tag=None,
                      position_available=None,
                      position_available_reverse=None,
                      long_short=True):
    """
    Pack order parameters and put buy/sell event in engine.
    :param buy_or_sell: ORDER_BUY or ORDER_SELL
    :param direction: DIRECTION_LONG or DIRECTION_SHORT
    :param order_price: order price
    :param order_qty: order quantity
    :param order_tag: order tag
    :param position_available: Available position to sell in the specified direction
    :param position_available_reverse: Available position to sell in the reverse direction of the specified
    :param long_short: If allowing to send order in the reverse direction
    :return: list of order params, updated_position_available, updated_position_available_reverse, is_order_split
    """
    reverse_direction = DIRECTION_SHORT if direction == DIRECTION_LONG else DIRECTION_LONG
    sell_direction = direction if buy_or_sell == SELL else reverse_direction
    buy_direction = reverse_direction if buy_or_sell == SELL else direction

    if buy_or_sell == SELL and (position_available is None or not long_short):
        sell_qty = order_qty
        buy_qty = 0
    elif buy_or_sell == BUY and (position_available_reverse is None or not long_short):
        sell_qty = 0
        buy_qty = order_qty
    else:
        position_for_sell = position_available if buy_or_sell == SELL else position_available_reverse
        sell_qty = min(position_for_sell, order_qty)
        buy_qty = max(0, order_qty - position_for_sell)
        if buy_or_sell == SELL:
            position_available -= sell_qty
        else:
            position_available_reverse -= sell_qty

    return [[{
        'action': SELL,
        'direction': sell_direction,
        'price': order_price,
        'qty': sell_qty,
        'tag': order_tag
    }, {
        'action': BUY,
        'direction': buy_direction,
        'price': order_price,
        'qty': buy_qty,
        'tag': order_tag
    }], position_available, position_available_reverse, sell_qty > 0 and buy_qty > 0]


def update_position_avg_price(position_qty_list, cma_price_list, trade_action, trade_direction, trade_price, trade_qty):
    """
    Update position quantity and calculate average prices with a new trade.
    Long/short positions are updated separately.
    Moving average price of current position is only updated on a buy trade, and does not change on a sell trade.
    :param position_qty_list: List of long and short position qty.
    :param cma_price_list: List of cumulative moving average prices of long and short positions.
    :param trade_action: 0 - buy, 1 - sell
    :param trade_direction: 0 - long, 1 -short
    :param trade_price: float
    :param trade_qty: int
    :return: None.
    """
    if trade_action == 0:  # update CMA price and qty for buy orders
        qty = position_qty_list[trade_direction]
        cma_price = cma_price_list[trade_direction]
        cma_price_list[trade_direction] = float(cma_price * qty + trade_price * trade_qty) / (qty + trade_qty)
        position_qty_list[trade_direction] += trade_qty
    else:  # For sell orders, only update qty. CMA price does not change.
        position_qty_list[trade_direction] -= trade_qty
        if position_qty_list[trade_direction] == 0:
            cma_price_list[trade_direction] = 0.0


def update_position_avg_price_2way(cma_price, position_qty, trade_action, trade_direction, trade_price, trade_qty):
    """
    Update position quantity and calculate average prices with a new trade.
    Long/short positions are updated together, i.e. sell long == buy short.
    Moving average price of current position is only updated when the position direction flips.
    :param cma_price: Cumulative moving average prices of current position, either long or short.
    :param position_qty: Position qty. Positive: long, negative: short.
    :param trade_action: 0 - buy, 1 - sell
    :param trade_direction: 0 - long, 1 -short
    :param trade_price: float
    :param trade_qty: int
    :return: int, float, float. New position qty, average price and realized gain.

    **Note**: Returned realized gain is not scaled with contract unit.
    """
    if trade_action != trade_direction:  # short
        trade_qty *= -1
    position_qty_new = position_qty + trade_qty

    if position_qty_new == 0:
        cma_price_new = 0.0
    elif position_qty == 0 or (position_qty > 0) != (position_qty_new > 0):
        cma_price_new = float(trade_price)
    elif (position_qty > 0) == (trade_qty > 0):
        cma_price_new = float(cma_price * position_qty + trade_price * trade_qty) / position_qty_new
    else:
        cma_price_new = cma_price

    if position_qty != 0 and ((position_qty > 0) != (trade_qty > 0)):
        realized_gain = (trade_price - cma_price) * (
            2 * int(position_qty > 0) - 1) * min(abs(position_qty), abs(trade_qty))
    else:
        realized_gain = 0

    return cma_price_new, position_qty_new, realized_gain