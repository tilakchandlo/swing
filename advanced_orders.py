"""
Adaptive order reducing timing risk.
"""


from datetime import datetime
from constants import *


class AdaptiveOrder:
    """
    Adaptively change pending order price to make it filled as soon as possible for minimal timing risk.
    """

    # Order states
    INIT, REQ, PENDING, FILLED, CANCELLED = 'INIT', 'REQ', 'PENDING', 'FILLED', 'CANCELLED'

    # Order modes
    # PATIENT: order price is the price specified by user.
    # ACCELERATED: order price is the more favor one btw last price yielding 1 tick and midpoint of bid/ask.
    # URGENT: order price is the less favor one btw last price yielding 1 tick and midpoint of bid/ask.
    # PANIC: order price is the market price.
    PATIENT, ACCELERATED, URGENT, PANIC = 'PATIENT', 'ACCELERATED', 'URGENT', 'PANIC'

    # Max limits of order pending time for different modes in seconds
    TIME_LIMIT = {PATIENT: float('inf'), ACCELERATED: float('inf'), URGENT: float('inf'), PANIC: float('inf')}

    def __init__(self,
                 contract,
                 buy_or_sell,
                 direction,
                 order_qty,
                 order_price=None,
                 order_tag=None,
                 retry_step=3,
                 patient_max_retry=2,
                 accelerated_max_retry=3,
                 urgent_max_retry=0,
                 panic_max_retry=0,
                 max_slippage=10):

        self.contract = contract
        self.buy_or_sell = buy_or_sell
        self.direction = direction
        self.order_price = order_price
        self.order_qty = order_qty
        self.order_tag = order_tag
        self.retry_step = retry_step
        self.state = self.INIT
        self.filled_qty = 0
        self.filled_price = 0.0
        self._long_short = 1 - int((self.buy_or_sell == BUY and self.direction == DIRECTION_LONG) or
                                   (self.buy_or_sell == SELL and self.direction == DIRECTION_SHORT))
        self._price_bound = order_price + (1 - 2 * self._long_short) * max_slippage * self.contract.tick
        self._order_mode_stack = [[self.PANIC, panic_max_retry], [self.URGENT, urgent_max_retry],
                                  [self.ACCELERATED, accelerated_max_retry], [self.PATIENT, patient_max_retry]]
        while self._order_mode_stack[-1][1] <= 0:
            self._order_mode_stack.pop()
        self.last_order_id = None
        self._last_order_time = None
        self._last_order_price = None
        self._last_order_mode = None

    def __repr__(self):
        return (
            "AdaptiveOrder {}: {} {} price={} qty={} state={} order_mode_stack={} last_order_id={} last_order_mode={}"
            " last_order_price={} last_order_time={} filled_qty={} filled_price={} bound={} retry_step={}".format(
                self.order_tag, ('buy', 'sell')[int(self.buy_or_sell == SELL)], self.direction, self.order_price,
                self.order_qty, self.state, self._order_mode_stack, self.last_order_id, self._last_order_mode,
                self._last_order_price, self._last_order_time, self.filled_qty, self.filled_price, self._price_bound,
                self.retry_step))

    def on_tick(self):
        d = 1 - 2 * self._long_short
        last_price = self.contract.last
        tick = self.contract.tick
        if self.state == self.INIT:
            if not self._order_mode_stack or d * (self.contract.last - self._price_bound) > 0:
                self.state = self.CANCELLED
                return ORDER_CANCELLED, None
            midpoint_price = round(
                round((self.contract.bid + self.contract.ask) / 2.0 / tick) * tick, self.contract.decimal)
            if self._order_mode_stack[-1][0] == self.PATIENT:
                order_price = (min, max)[self._long_short](last_price, midpoint_price)
                if self._last_order_price is None and self.order_price is not None:  # first try w/ specified price
                    order_price = (min, max)[self._long_short](self.order_price, order_price)
            elif self._order_mode_stack[-1][0] == self.ACCELERATED:
                order_price = (min, max)[self._long_short](last_price + d * tick, midpoint_price)
            elif self._order_mode_stack[-1][0] == self.URGENT:
                order_price = (max, min)[self._long_short](last_price + d * tick, midpoint_price)
            else:  # PANIC mode
                order_price = (self.contract.ask, self.contract.bid)[self._long_short]  # market_price

            order_qty = self.order_qty - self.filled_qty
            order_params = {
                'action': self.buy_or_sell,
                'direction': self.direction,
                'price': order_price,
                'qty': order_qty,
                'tag': self.order_tag
            }
            self.state = self.REQ
            return ORDER_OPEN, order_params
        elif self.state == self.REQ:
            return None, None
        elif self.state == self.PENDING:
            time_delta = (datetime.utcnow() - self._last_order_time).total_seconds()
            if (time_delta > self.TIME_LIMIT[self._last_order_mode] or
                    d * (last_price - self._last_order_price) >= self.retry_step * tick or
                    d * (last_price - self._price_bound) > 0):
                return ORDER_OPEN, {'action': 'CANCEL', 'order_id': self.last_order_id}
            else:
                return None, None
        else:  # FILLED
            return ORDER_CLOSED, None

    def on_buysell_success(self, order_id, order_price):
        self.last_order_id = int(order_id)
        self._last_order_time = datetime.utcnow()
        self._last_order_price = order_price
        self._last_order_mode = self._order_mode_stack[-1][0]
        self.state = self.PENDING

        self._order_mode_stack[-1][1] -= 1
        while self._order_mode_stack[-1][1] <= 0:
            self._order_mode_stack.pop()

    def on_buysell_fail(self):
        self.state = self.INIT

    def on_trade_update(self, trade_price, trade_qty):
        self.filled_price = (self.filled_price * self.filled_qty + trade_price * trade_qty) / (
            self.filled_qty + trade_qty)
        self.filled_qty += trade_qty

    def on_order_status(self, order_status):
        if order_status == ORDER_CLOSED or self.filled_qty == self.order_qty:
            self.state = self.FILLED
        else:
            self.state = self.INIT