"""
Definition of the GridOsc trading logic, which constitutes the basic components of swing trading.
"""


from math import ceil, floor
from constants import *
from strategy import INIT, REQ, SPLIT
from strategy import calc_order_params, update_position_avg_price_2way


class GridOsc:
    """
    Oscillatory trading on a pre-defined price grid. Support trailing buy/sell.
    """

    def __init__(self,
                 logger,
                 tag,
                 contract,
                 low_bound,
                 n_grids,
                 grid_height,
                 low_ext,
                 high_ext,
                 trail_amt,
                 qty_base_long,
                 qty_base_short,
                 qty_offset_long,
                 qty_offset_short,
                 last_order_price,
                 k_init,
                 qty_base_scaling=True,
                 position_qty_cap_min=-2**64,
                 position_qty_cap_max=2**64,
                 order_qty_cap_long=2**64,
                 order_qty_cap_short=2**64):
        """
        :param tag: str. Name tag of the zone.
        :param contract: Contract object.
        :param low_bound: float. Initial lower price bound of the zone.
        :param n_grids: int. Initial number of grids.
        :param grid_height: float. Price grid height.
        :param low_ext: bool. If lower bound can be extended.
        :param high_ext: bool. If higher bound can be extended.
        :param trail_amt: float. Price trailing amount to trigger an order.
        :param qty_base_long: int. Base order quantity A for one-grid swing long.
        :param qty_base_short: int. Base order quantity A for one-grid swing short.
        :param qty_offset_long: int. Base offset order quantity for the long side.
        :param qty_offset_short: int. Base offset order quantity for the short side.
        :param k_init: int. Initial value of offset order quantity scale k.
        :param qty_base_scaling: bool. If scale base order qty based on price swing range.
        :param last_order_price: float. Price of last successfully submitted order.
        :param position_qty_cap_min: int. Minimal position qty (-inf, inf) to keep.
        :param position_qty_cap_max: int. Maximal position qty (-inf, inf) to keep.
        :param order_qty_cap_long: int. Maximal order qty for long [0, inf).
        :param order_qty_cap_short: int. Maximal order qty for short [0, inf).
        """
        self.logger = logger

        # tag, contract
        self.tag = tag
        self.contract = contract

        # Grids planning
        self.n_grids = n_grids
        self.ph = grid_height
        self.bounds = [low_bound, round(low_bound + n_grids * self.ph, contract.decimal)]
        self.ext = (low_ext, high_ext)

        # Trailing and oscillatory parameters
        self.pt = trail_amt
        self.qa = [qty_base_long, qty_base_short]
        self.qn = [qty_offset_long, qty_offset_short]
        self.order_qty_scaling = qty_base_scaling
        self.position_qty_caps = [position_qty_cap_min, position_qty_cap_max]
        self.order_qty_caps = [order_qty_cap_long, order_qty_cap_short]

        # Oscillator states
        self.state = INIT
        self.last_order_price = last_order_price
        self.peak = [last_order_price, last_order_price]  # price valley and ridge for long and short
        self._position_qty = 0  # Position quantity. >0: long, <0: short.
        self._cma_price = 0.0  # Cumulative moving average price.
        self._k = k_init  # initial value of the volume offset scale k
        self._k_profit = 0.0  # Accumulated profit since the last change of k value
        self._k_profit_th = (self.bounds[1] - self.bounds[0]) * (
            self.n_grids * min(self.qa) + self._k * min(self.qn)) * self.contract.unit

    def __repr__(self):
        return ("{}: n_grids={} bounds={} ext={} qa={} qn={} state={} last_order_price={} peak={} "
                "position_qty={} cma_price={} k={} k_profit={} k_profit_th={}").format(
                    self.tag, self.n_grids, self.bounds, self.ext, self.qa, self.qn, self.state, self.last_order_price,
                    self.peak, self._position_qty, self._cma_price, self._k, self._k_profit, self._k_profit_th)

    def _r(self, price):
        return round(price, self.contract.decimal)

    def _update_last_order_price(self, last_order_price):
        self.last_order_price = last_order_price
        self.peak = [last_order_price, last_order_price]

    def _zone_expand(self, price):
        for direction in (0, 1):
            d = 1 - 2 * direction
            if self.ext[direction] and d * (price - self.bounds[direction]) < 0:
                n_grids_ext = int(ceil(d * (self.bounds[direction] - price) / self.ph))
                self.n_grids += n_grids_ext
                self.bounds[direction] = self._r(self.bounds[direction] - d * n_grids_ext * self.ph)
                self._k_profit_th = (self.bounds[1] - self.bounds[0]) * (
                    self.n_grids * min(self.qa) + self._k * min(self.qn)) * self.contract.unit
                break

    def on_tick_update(self, price):
        # Update peak prices
        self.peak[0] = min(self.peak[0], price)
        self.peak[1] = max(self.peak[1], price)

        # Expand zone if necessary
        if any(self.ext):
            self._zone_expand(price)

    def on_tick_trade(self, trade_price, position_long, position_short):
        """
        Trading rules and states update when receiving market data.
        :params trade_price: Latest price used to determine trading conditions.
        :params position_long: Current available long position quantity to sell.
        :params position_short: Current available short position quantity to sell.
        """
        # Check state
        order_params_list = []
        if self.state in (REQ, SPLIT):
            return order_params_list, position_long, position_short

        # Check if order conditions are met in either long or short direction.
        # 1. peak to last trade price > h0;  2. trailing > pt;  3. last price and last order price in different grids.
        position_qty = position_long - position_short
        pos_qty_caps = (self.position_qty_caps[1] - position_qty, position_qty - self.position_qty_caps[0])
        for direction in (0, 1):
            peak = self.peak[direction]
            d = 1 - 2 * direction
            if self._r(d * (self.last_order_price - trade_price)) >= self.ph \
                    and self._r(d * (trade_price - peak)) >= self.pt:
                scale = int(floor(d * (self.last_order_price - trade_price) / self.ph))
                if not self.order_qty_scaling:
                    scale = min(1, scale)
                order_qty = int(scale > 0) * (scale * self.qa[direction] + self._k * self.qn[direction])
                self.logger.debug("{}: {} last_order_price={} peak={} trade_price={} scale={} k={} order_qty={}".format(
                    self.tag, ('long', 'short')[direction], self.last_order_price, peak, trade_price, scale, self._k,
                    order_qty))
                order_qty = min(order_qty, pos_qty_caps[direction])
                self.logger.debug("{}: {} pos={}({},{}) pos_cap_{}={} qty_cap={} updated order_qty={}".format(
                    self.tag, ('long', 'short')[direction], position_qty, position_long, position_short,
                    ('max', 'min')[direction], (self.position_qty_caps[1], self.position_qty_caps[0])[direction],
                    pos_qty_caps[direction], order_qty))
                order_qty = min(order_qty, self.order_qty_caps[direction])
                self.logger.debug("{}: {} order_qty_cap={} updated order_qty={}".format(
                    self.tag, ('long', 'short')[direction], self.order_qty_caps[direction], order_qty))
                if order_qty > 0:  # Make order parameters list only if order qty > 0.
                    order_params_list, position_long, position_short, is_order_split = calc_order_params(
                        (BUY, SELL)[direction],
                        DIRECTION_LONG,
                        trade_price,
                        order_qty,
                        order_tag=self.tag,
                        position_available=position_long,
                        position_available_reverse=position_short)
                    # State transition to REQ to wait for order submission
                    self.state = SPLIT if is_order_split else REQ
                    break
        return order_params_list, position_long, position_short

    def on_buy_sell_fail(self):
        if self.state == SPLIT:
            self.state = REQ
        elif self.state == REQ:
            self.state = INIT

    def on_buy_sell_success(self, order_price):
        if self.state == SPLIT:
            self.state = REQ
        elif self.state == REQ:
            self.state = INIT
        self._update_last_order_price(order_price)

    def on_trade_update(self, trade_action, trade_direction, trade_price, trade_qty):
        self.logger.debug("{}: trade update Begin: position_qty={} cma_price={} k={} k_profit={} k_profit_th={}".format(
            self.tag, self._position_qty, self._cma_price, self._k, self._k_profit, self._k_profit_th))
        self._cma_price, self._position_qty, realized_gain = update_position_avg_price_2way(
            self._cma_price, self._position_qty, trade_action, trade_direction, trade_price, trade_qty)
        self._k_profit += realized_gain * self.contract.unit
        if self._k_profit > self._k_profit_th:
            self._k += 1
            self._k_profit = 0.0
            self._k_profit_th += (self.bounds[1] - self.bounds[0]) * min(self.qn) * self.contract.unit
        self.logger.debug(
            "{}: trade update End: unscaled_gain={} position_qty={} cma_price={} k={} k_profit={} k_profit_th={}".
            format(self.tag, realized_gain, self._position_qty, self._cma_price, self._k, self._k_profit,
                   self._k_profit_th))