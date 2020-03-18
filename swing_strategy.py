# encoding: utf-8

from math import floor
from constants import DIRECTION, DIRECTION_LONG, DIRECTION_SHORT, PRICE, BUY, SELL
from strategy import REQ, SPLIT
from strategy import calc_order_params
from strategy import Strategy
from advanced_orders import AdaptiveOrder
from grid_osc_strategy import GridOsc


# Swing strategy user parameter field names
OPEN_PRICE = 'OPEN_PRICE'
OPEN_VOLUME = 'OPEN_VOLUME'
BASE_VOLUME = 'BASE_VOLUME'
TRAIL_PRICE_TICKS = 'TRAIL_PRICE_TICKS'
STOPWIN_BASE_PERCENTAGE = 'STOPWIN_BASE_PERCENTAGE'
TRAIL_PERCENTAGE = 'TRAIL_PERCENTAGE'
OPEN_OFFSET_VOLUME = 'OPEN_OFFSET_VOLUME'
CLOSE_OFFSET_VOLUME = 'CLOSE_OFFSET_VOLUME'
START_ZONE = 'START_ZONE'
TREND_REVERSAL_PRICE_TRAIL_RATIO = 'TREND_REVERSAL_PRICE_TRAIL_RATIO'
MIN_OSC_HEIGHT = 'MIN_OSC_HEIGHT'
RISKY_ZONE_ACTIVATE_LOSS_RATIO = 'RISKY_ZONE_ACTIVATE_LOSS_RATIO'


class SwingStrategy(Strategy):
    """
    Zone-based swing trading strategy by trailing stop.
    Zone planning, trailing and other parameters are input or fixed, which can be optimized from historical data.
    """

    # Strategy parameters
    ZONE_NAMES = 'Net', 'Inc', 'Osc', 'Dec'
    N_GRIDS = 8  # Number of grids in one zone. Even numbers only.
    # MINIMUM_GRID_HEIGHT = 3  # Minimum grid height p_h in number of tick size. Guaranteed by front-end logic.
    N_GRIDS_CANCEL_ORDER = 12  # Number of grids between an order price and last price before cancelling the order.

    TREND_REVERSAL_QTY_RATIO = 0.4  # Open qty ratio relative to q_max at trend reversal.
    TREND_REVERSAL_RETRY_STEP = 3  # How many ticks slipped before resend trend reversal order.
    TREND_REVERSAL_PATIENT_MAX_RETRY = 1  # Max retries for trend reversal patient order mode.
    TREND_REVERSAL_ACCELERATED_MAX_RETRY = float('inf')  # Max retries for trend reversal accelerated order mode.
    # TREND_REVERSAL_MAX_SLIPPAGE = 15  # Max slippage ticks for trend reversal.

    RISKY_INIT_MIN_POSITION_RATIO = 0.8  # Position qty ratio relative to max qty to determine cut qty.
    RISKY_INIT_CUT_QTY_RATIO_1 = 1 / 3.0  # Cut qty ratio if position qty >= max qty
    RISKY_INIT_CUT_QTY_RATIO_2 = 1 / 4.0  # Cut qty ratio if position qty >= MIN_POSITION_RATIO
    RISKY_INIT_RETRY_STEP = 3  # How many ticks slipped before resend RISKY_INIT order.
    RISKY_INIT_PATIENT_MAX_RETRY = 0  # Max retries for RISKY_INIT patient order mode.
    RISKY_INIT_ACCELERATED_MAX_RETRY = float('inf')  # Max retries for RISKY_INIT accelerated order mode.
    RISKY_INIT_MAX_SLIPPAGE = float('inf')  # Max slippage ticks for RISKY_INIT.

    RISKY_OSC_BUY_BACK_QTY_RATIO = 0.5  # Buy back base qty ratio for osc in RISkY zone
    RISKY_OSC_SELL_OFF_QTY_RATIO = 1 / 3.0  # Sell off base qty ratio for osc in RISKY zone

    STOP_GAIN_LOWER_BOUND_TH = 0.02  # Additional gain ratio in the lower bound for trailing stop
    STOP_RETRY_STEP = 3  # How many ticks slipped before resend stop order.
    STOP_PATIENT_MAX_RETRY = 1  # Max retries for stop patient order mode.
    STOP_ACCELERATED_MAX_RETRY = float('inf')  # Max retries for stop accelerated order mode.
    STOP_MAX_SLIPPAGE = float('inf')  # Max slippage ticks for stop.

    # Strategy states
    (SWING_START, SWING_GRID_OSC, SWING_REVERSAL, SWING_RISKY_INIT, SWING_RISKY_OSC, SWING_STOP, SWING_FINISH) = range(
        800, 800 + 7)

    def __init__(self):
        Strategy.__init__(self)

        # Strategy parameters
        self.direction = None  # str. Initial long or short direction.
        self.start_zone = None  # str. Starting operating zone name.
        self.p0 = None  # float. Starting price as the middle of start zone.
        self.pls = None  # float. Price trailing percentage as indicator of trend reversal.
        self.ph = None  # float. Minimum swing price height.
        self.pt = None  # float. Universal price trailing amount.
        self.q_max = 0  # int. Max position quantity.
        self.qa = 0  # int. Oscillatory base quantity.
        self.q_offset = {zone_name: (0, 0) for zone_name in self.ZONE_NAMES}  # Oscillatory quantity offsets.
        self.g_risky = None  # float. Risky zone activate loss ratio.
        self.g0 = None  # float. Profit gain starting ratio for stop win.
        self.gt = None  # float. Profit gain trailing ratio for stop win.

        # Strategy states
        self._state = self.SWING_GRID_OSC
        self._long_short = None  # Binary trading state. 0: long, 1: short.
        self._state_cleanup = False  # If the current state in the cleanup stage.
        self._next_state_after_cleanup = None  # The next state after cleanup finishes.

        # SWING_GRID_OSC
        self._zones = {}  # Dict of zone objects.
        self._start_zone = None
        self._start_zone_mid_price = None
        self._active_zone = None  # Reference to the current active operating zone.
        self._dec_peak = None  # Peak price in Dec zone.

        # SWING_REVERSAL
        self._reversal_orders = []

        # SWING_RISKY_INIT & SWING_RISKY_OSC
        self._risky_base_val = 0.0
        self._risky_base_qty = 0
        self._risky_cut_qty = 0
        self._risky_cut_price = 0.0
        self._risky_init_order_qty = 0
        self._risky_init_orders = []
        self._risky_osc_zone = None

        # SWING_STOP
        self._max_gain = float('-inf')  # max profit for trailing close
        self._stop_orders = []

    def strategy_config_params(self, strategy_params):
        """
        Config strategy specific parameters set by user. Read-only during strategy running.
        :param strategy_params: Strategy parameters. If None, default all params.
        """
        if strategy_params is None:
            self.start_zone = None
            self.direction = None
            self.p0 = self.pls = self.ph = self.pt = None
            self.q_max = None
            self.qa = 0
            self.q_offset = {zone_name: (0, 0) for zone_name in self.ZONE_NAMES}
            self.g_risky = None
            self.g0 = self.gt = None
        else:
            self.start_zone = strategy_params[START_ZONE]
            self.direction = strategy_params[DIRECTION]
            self.p0 = strategy_params[OPEN_PRICE]
            self.pls = strategy_params[TREND_REVERSAL_PRICE_TRAIL_RATIO]
            self.ph = strategy_params[MIN_OSC_HEIGHT]
            self.pt = strategy_params[TRAIL_PRICE_TICKS]
            self.q_max = strategy_params[OPEN_VOLUME]
            self.qa = strategy_params[BASE_VOLUME]
            self.q_offset = {
                zone_name: (self.qa * strategy_params[OPEN_OFFSET_VOLUME][zone_name],
                            self.qa * strategy_params[CLOSE_OFFSET_VOLUME][zone_name])
                for zone_name in self.ZONE_NAMES
            }
            self.g_risky = strategy_params[RISKY_ZONE_ACTIVATE_LOSS_RATIO]
            self.g0, self.gt = strategy_params[STOPWIN_BASE_PERCENTAGE], strategy_params[TRAIL_PERCENTAGE]

    def strategy_config_on_start(self):
        """
        Resets and configs of strategy attributes on start.
        """
        self._state = self.SWING_START
        self._long_short = int(self.direction == DIRECTION_SHORT)
        self._state_cleanup = False
        self._next_state_after_cleanup = None

        # SWING_GRID_OSC
        self._zones = {}
        self._start_zone = self.start_zone
        self._start_zone_mid_price = self.p0
        self._active_zone = None
        self._dec_peak = (2 * self._long_short - 1) * float('inf')

        # SWING_REVERSAL
        self._reversal_orders = []

        # SWING_RISKY_INIT & SWING_RISKY_OSC
        self._risky_base_val = self._principal
        self._risky_base_qty = 0
        self._risky_cut_qty = 0
        self._risky_cut_price = 0.0
        self._risky_init_order_qty = 0
        self._risky_init_orders = []
        self._risky_osc_zone = None

        # SWING_STOP
        self._max_gain = float('-inf')
        self._stop_orders = []

    def strategy_config_on_stop(self):
        """
        Clean up actions of strategy attributes on stop.
        """
        pass

    def _swing_start_run(self):
        self.logger.debug("SWING_START: waiting for trigger. long_short={} open price={} last price={}".format(
            self._long_short, self.p0, self.contract.last))
        if (1 - 2 * self._long_short) * (self.contract.last - self.p0) > 0:
            return False
        if 'Net' not in self.start_zone:
            self._state = self.SWING_GRID_OSC
            self.logger.debug("SWING_START -> SWING_GRID_OSC: Now")
        else:
            self._state = self.SWING_REVERSAL
            self._long_short = 1 - self._long_short  # flip _long_short to be reversed later
            self.logger.debug("SWING_START -> SWING_REVERSAL: Now")
        return True

    def _setup_zones(self, start_zone_name=None, start_zone_mid_price=None):
        """
        Initialize or reset zone planning.
        """
        if start_zone_name is None:
            start_zone_index = 0  # Start with Net zone when flipping b/w long/short.
        else:
            start_zone_index = self.ZONE_NAMES.index(start_zone_name)
        if start_zone_mid_price is None:
            start_zone_mid_price = self.contract.last

        d = 1 - 2 * self._long_short
        open_bound = start_zone_mid_price - d * (self.N_GRIDS / 2 + start_zone_index * self.N_GRIDS) * self.ph
        close_bound = open_bound + d * self.N_GRIDS * self.ph
        for zone_name in self.ZONE_NAMES:
            low_bound = (open_bound, close_bound)[self._long_short]
            low_bound_ext = high_bound_ext = False
            if (zone_name == self.ZONE_NAMES[0] and self._long_short == 0) or (zone_name == self.ZONE_NAMES[-1] and
                                                                               self._long_short == 1):
                low_bound_ext = True
            if (zone_name == self.ZONE_NAMES[-1] and self._long_short == 0) or (zone_name == self.ZONE_NAMES[0] and
                                                                                self._long_short == 1):
                high_bound_ext = True
            qty_offset_long = self.q_offset[zone_name][self._long_short]
            qty_offset_short = self.q_offset[zone_name][1 - self._long_short]
            self._zones[zone_name] = GridOsc(
                logger=self.logger,
                tag=zone_name,
                contract=self.contract,
                low_bound=low_bound,
                n_grids=self.N_GRIDS,
                grid_height=self.ph,
                low_ext=low_bound_ext,
                high_ext=high_bound_ext,
                trail_amt=self.pt,
                qty_base_long=self.qa,
                qty_base_short=self.qa,
                qty_offset_long=qty_offset_long,
                qty_offset_short=qty_offset_short,
                last_order_price=start_zone_mid_price,
                k_init=0,
                qty_base_scaling=True,
                position_qty_cap_min=(0, -2**64)[self._long_short],
                position_qty_cap_max=(2**64, 0)[self._long_short])

            open_bound = close_bound
            close_bound = open_bound + d * self.N_GRIDS * self.ph

        self._active_zone = self._zones[self.ZONE_NAMES[start_zone_index]]

    def _is_trailing_stop_on_gain_triggered(self):
        """
        Trace unrealized gain and determine if trailing stop is triggerred.
        :return: bool
        """
        gain_lower_bound = round(self._principal * self.g0 * (1 - self.gt - self.STOP_GAIN_LOWER_BOUND_TH), 2)
        is_gain_valid = self._gain >= gain_lower_bound
        if not is_gain_valid:
            self._max_gain = float('-inf')
        self._max_gain = max(self._gain, self._max_gain)
        target_gain = round(self.g0 * self._principal, 2)
        trailing_amount = round(self._max_gain - self._gain, 2)
        trailing_target = round(self.gt * self._max_gain, 2)
        is_triggered = is_gain_valid and self._max_gain >= target_gain and trailing_amount >= trailing_target
        self.logger.debug(
            "SWING Trailing Stop: LowBound = {}  gain = {}  is_valid = {}  max_gain = {}  target_gain = {} "
            "trail_amt = {}  trail_target = {}  triggered = {}".format(gain_lower_bound, self._gain, is_gain_valid,
                                                                       self._max_gain, target_gain, trailing_amount,
                                                                       trailing_target, is_triggered))
        return is_triggered

    def _swing_grid_osc_transition(self):
        """
        State transitions from SWING_GRID_OSC.
        :return: bool. If current state is in blocking or in transition. If True, do not run state logic.
        """
        # Blocking on order REQ
        if self._active_zone is not None and self._active_zone.state in (REQ, SPLIT):
            return True

        # Cleanup in progress
        if self._state_cleanup:
            self.logger.debug("SWING_GRID_OSC: state_cleanup in progress.")
            if not self.order_dict:
                self._state = self._next_state_after_cleanup
                self._state_cleanup = False
                self._next_state_after_cleanup = None
                self.logger.debug("SWING_GRID_OSC -> {}: After Cleanup".format(self._state))

        # To SWING_STOP
        elif self._is_trailing_stop_on_gain_triggered():
            if self.order_dict:
                self._state_cleanup = True
                self._next_state_after_cleanup = self.SWING_STOP
                self.cancel_all_orders()
                self.logger.debug("SWING_GRID_OSC -> SWING_STOP: Cancel orders")
            else:
                self._state = self.SWING_STOP
                self._state_cleanup = False
                self._next_state_after_cleanup = None
                self.logger.debug("SWING_GRID_OSC -> SWING_STOP: Now")

        # To SWING_REVERSAL
        elif self._active_zone is not None and 'Dec' in self._active_zone.tag:
            self._dec_peak = (max, min)[self._long_short](self._dec_peak, self.contract.last)
            reversal_trail = (1 - 2 * self._long_short) * (1 - self.contract.last / self._dec_peak)
            reversal_triggerred = reversal_trail > self.pls
            self.logger.debug(
                "SWING_GRID_OSC: _dec_peak={} last_price={} trail_ratio={} target_ratio={} reversal_triggerred={}".
                format(self._dec_peak, self.contract.last, reversal_trail, self.pls, reversal_triggerred))
            if reversal_triggerred:
                if self.order_dict:
                    self._state_cleanup = True
                    self._next_state_after_cleanup = self.SWING_REVERSAL
                    self.cancel_all_orders()
                    self.logger.debug("SWING_GRID_OSC -> SWING_REVERSAL: Cancel orders")
                else:
                    self._state = self.SWING_REVERSAL
                    self._state_cleanup = False
                    self._next_state_after_cleanup = None
                    self.logger.debug("SWING_GRID_OSC -> SWING_REVERSAL: Now")

        # To SWING_RISKY_INIT
        elif self._active_zone is not None and 'Net' in self._active_zone.tag:
            risky_init_value_trail_target = (1 - self.g_risky) * self._risky_base_val
            risky_init_value_trail_triggered = self._nlv < risky_init_value_trail_target
            position_qty = (1 - 2 * self._long_short) * (self._position_qty[0] - self._position_qty[1])
            if position_qty >= self.q_max:
                risky_init_order_qty = int(floor(position_qty * self.RISKY_INIT_CUT_QTY_RATIO_1))
            elif position_qty >= self.RISKY_INIT_MIN_POSITION_RATIO * self.q_max:
                risky_init_order_qty = int(floor(position_qty * self.RISKY_INIT_CUT_QTY_RATIO_2))
            else:
                risky_init_order_qty = 0
            risky_osc_min_order_qty = min(
                int(floor(r * risky_init_order_qty))
                for r in (self.RISKY_OSC_BUY_BACK_QTY_RATIO, self.RISKY_OSC_SELL_OFF_QTY_RATIO))
            self.logger.debug(
                "SWING_GRID_OSC -> SWING_RISKY_INIT: risky_base_val={} target_val={} nlv={} value_triggered={}"
                " order_qty={} osc_min_order_qty={}".format(self._risky_base_val, risky_init_value_trail_target,
                                                            self._nlv, risky_init_value_trail_triggered,
                                                            risky_init_order_qty, risky_osc_min_order_qty))
            if risky_init_value_trail_triggered and risky_init_order_qty > 0 and risky_osc_min_order_qty > 0:
                self._risky_init_order_qty = risky_init_order_qty
                self._risky_base_qty = position_qty
                if self.order_dict:
                    self._state_cleanup = True
                    self._next_state_after_cleanup = self.SWING_RISKY_INIT
                    self.cancel_all_orders()
                    self.logger.debug("SWING_GRID_OSC -> SWING_RISKY_INIT: Cancel orders")
                else:
                    self._state = self.SWING_RISKY_INIT
                    self._state_cleanup = False
                    self._next_state_after_cleanup = None
                    self.logger.debug("SWING_GRID_OSC -> SWING_RISKY_INIT: Now")

        return self._state_cleanup

    def _swing_risky_osc_transition(self):
        """
        State transitions from SWING_RISKY_OSC.
        :return: bool. If current state is in blocking or in transition. If True, do not run state logic.
        """
        # Blocking on order REQ
        if self._risky_osc_zone is not None and self._risky_osc_zone.state in (REQ, SPLIT):
            return True

        state_transition = True

        # Cleanup in progress
        if self._state_cleanup:
            self.logger.debug("SWING_RISKY_OSC: state_cleanup in progress.")
            if not self.order_dict:
                self._state = self._next_state_after_cleanup
                self._state_cleanup = False
                self._next_state_after_cleanup = None
                self.logger.debug("SWING_RISKY_OSC -> {}: After Cleanup".format(self._state))

        # To SWING_STOP
        elif self._is_trailing_stop_on_gain_triggered():
            if self.order_dict:
                self._state_cleanup = True
                self._next_state_after_cleanup = self.SWING_STOP
                self.cancel_all_orders()
                self.logger.debug("SWING_RISKY_OSC -> SWING_STOP: Cancel orders")
            else:
                self._state = self.SWING_STOP
                self._state_cleanup = False
                self._next_state_after_cleanup = None
                self.logger.debug("SWING_RISKY_OSC -> SWING_STOP: Now")

        # To SWING_GRID_OSC
        elif ((1 - 2 * self._long_short) * (self._position_qty[0] - self._position_qty[1]) >= self._risky_base_qty or
              self._nlv > self._risky_base_val):
            if self.order_dict:
                self._state_cleanup = True
                self._next_state_after_cleanup = self.SWING_GRID_OSC
                self.cancel_all_orders()
                self.logger.debug("SWING_RISKY_OSC -> SWING_GRID_OSC: Cancel orders")
            else:
                self._state = self.SWING_GRID_OSC
                self._state_cleanup = False
                self._next_state_after_cleanup = None
                self.logger.debug("SWING_RISKY_OSC -> SWING_GRID_OSC: Now")

        else:
            state_transition = False

        if state_transition and not self._state_cleanup:
            self._active_zone.peak[:] = self._risky_osc_zone.peak[:]
            self._active_zone.last_order_price = self._risky_osc_zone.last_order_price
            self._risky_osc_zone = None
            self._risky_base_val = self._nlv  # Reset risky zone base value to current nlv
            self._risky_base_qty = (1 - 2 * self._long_short) * (self._position_qty[0] - self._position_qty[1])
            self._risky_cut_qty = 0
            self._risky_cut_price = 0.0
            self.logger.debug("SWING_RISKY_OSC -> {}: NEW risky_base_val={} risky_base_qty={}".format(
                self._state, self._risky_base_val, self._risky_base_qty))

        return self._state_cleanup

    def _swing_grid_osc_run(self):
        # Initialize zone planning
        if not self._zones:
            self._setup_zones(self._start_zone, self._start_zone_mid_price)
        self.logger.debug(
            "SWING_GRID_OSC Zones:\n" + '\n'.join([str(self._zones[zone_name]) for zone_name in self.ZONE_NAMES]))

        # Update active zone status
        self._active_zone.on_tick_update(self.contract.last)
        self.logger.debug("SWING_GRID_OSC active zone update:\n{}".format(self._active_zone))

        # Check and switch active zone
        for direction in (0, 1):
            d = 1 - 2 * direction
            active_zone_index = self.ZONE_NAMES.index(self._active_zone.tag)
            new_active_zone_index = active_zone_index
            new_active_zone = self._zones[self.ZONE_NAMES[new_active_zone_index]]
            while (not new_active_zone.ext[direction] and
                   d * (new_active_zone.bounds[direction] - self.contract.last) >= self.ph):
                new_active_zone_index -= d * (1 - 2 * self._long_short)
                new_active_zone = self._zones[self.ZONE_NAMES[new_active_zone_index]]
            if new_active_zone_index != active_zone_index:
                new_active_zone.last_order_price = self._active_zone.last_order_price
                new_active_zone.peak[:] = self._active_zone.peak[:]
                new_active_zone.on_tick_update(self.contract.last)  # expand new zone if needed
                self._active_zone = new_active_zone
                self.logger.debug("SWING_GRID_OSC: active zone switched:\n{}".format(self._active_zone))
                break

        # Run active zone rules
        position_available_long, position_available_short = [
            self.portfolio_obj.get_traded_qty(self.account_id, self.contract.instrument_id, direction, real_time=False)
            for direction in (DIRECTION_LONG, DIRECTION_SHORT)
        ]
        order_params_list, _, _ = self._active_zone.on_tick_trade(self.contract.last, position_available_long,
                                                                  position_available_short)
        if order_params_list:
            self.logger.debug("SWING_GRID_OSC order_params_list: {}".format(order_params_list))
        self.send_limit_order(order_params_list)

        # Cancel OSC orders that are far away from current price
        orders_to_cancel = []
        for order in self.order_dict.values():
            if abs(self.contract.last - order.price) > self.N_GRIDS_CANCEL_ORDER * self.ph:
                orders_to_cancel.append(order.order_id)
        if orders_to_cancel:
            self.cancel_orders(orders_to_cancel)
            self.logger.debug("SWING_GRID_OSC orders_to_cancel: {}".format(orders_to_cancel))

    def _swing_reversal_run(self):
        # Initialize reversal orders
        if not self._reversal_orders:
            max_slippage = int(((self.N_GRIDS * self.ph) / 2.0 + self.ph) / self.contract.tick) + 1
            if self._zones:
                max_slippage = max(max_slippage,
                                   int(((1 - 2 * self._long_short) *
                                        (self.contract.last - self._zones['Dec'].bounds[self._long_short]) + self.ph) /
                                       self.contract.tick) + 1)
            self._long_short = 1 - self._long_short
            position_availabe = self._position_qty[self._long_short]
            position_availabe_reverse = self._position_qty[1 - self._long_short]
            order_qty = int(round(
                self.TREND_REVERSAL_QTY_RATIO * self.q_max)) - (position_availabe - position_availabe_reverse)
            order_params_list, _, _, _ = calc_order_params(
                BUY, (DIRECTION_LONG, DIRECTION_SHORT)[self._long_short], self.contract.last, order_qty,
                'SWING_REVERSAL', position_availabe, position_availabe_reverse)
            order_params_list[0]['tag'] = 'SWING_REVERSAL_SELL'
            order_params_list[1]['tag'] = 'SWING_REVERSAL_BUY'
            for order_params in order_params_list:
                if order_params['qty'] > 0:
                    reversal_order = AdaptiveOrder(
                        contract=self.contract,
                        buy_or_sell=order_params['action'],
                        direction=order_params['direction'],
                        order_qty=order_params['qty'],
                        order_price=order_params['price'],
                        order_tag=order_params['tag'],
                        retry_step=self.TREND_REVERSAL_RETRY_STEP,
                        patient_max_retry=self.TREND_REVERSAL_PATIENT_MAX_RETRY,
                        accelerated_max_retry=self.TREND_REVERSAL_ACCELERATED_MAX_RETRY,
                        max_slippage=max_slippage)
                    self._reversal_orders.append(reversal_order)
                    self.logger.debug("SWING_REVERSAL: Reversal order created: {}".format(reversal_order))

        # Run reversal orders
        order_finished = []
        for reversal_order in self._reversal_orders:
            order_finished.append(self.run_adaptive_order(reversal_order))
            self.logger.debug("SWING_REVERSAL: Reversal order run: {}".format(reversal_order))
        self.logger.debug("SWING_REVERSAL: Reversal order finished = {}".format(order_finished))

        # Reversal finishes
        if all(order_finished):
            filled_qty = 0
            filled_price = 0.0
            for reversal_order in self._reversal_orders:
                filled_price = (filled_qty * filled_price + reversal_order.filled_qty * reversal_order.filled_price) / (
                    filled_qty + reversal_order.filled_qty)
                filled_qty += reversal_order.filled_qty
            filled_price = round(round(filled_price / self.contract.tick) * self.contract.tick, self.contract.decimal)

            # switch to GRID_OSC state
            self._state = self.SWING_GRID_OSC
            self._zones = {}
            self._start_zone = 'Net'
            self._start_zone_mid_price = filled_price if filled_qty > 0 else self._reversal_orders[0].order_price
            self._active_zone = None
            self._dec_peak = (2 * self._long_short - 1) * float('inf')

            # Reset RISKY states
            self._risky_base_val = self._nlv
            self._risky_base_qty = (1 - 2 * self._long_short) * (self._position_qty[0] - self._position_qty[1])
            self._risky_cut_qty = 0
            self._risky_cut_price = 0.0
            self._risky_init_order_qty = 0
            self._risky_init_orders = []
            self._risky_osc_zone = None

            # Clean up reversal states
            self._reversal_orders = []
            self.logger.debug("SWING_REVERSAL: Finished. filled_qty={}  filled_price={}".format(
                filled_qty, filled_price))
            self.logger.debug("SWING_REVERSAL -> SWING_GRID_OSC")

    def _swing_risky_init_run(self):
        # Initialize RISKY_INIT order
        if not self._risky_init_orders:
            position_availabe = self._position_qty[self._long_short]
            position_availabe_reverse = self._position_qty[1 - self._long_short]
            order_params_list, _, _, _ = calc_order_params(
                SELL, (DIRECTION_LONG, DIRECTION_SHORT)[self._long_short], self.contract.last,
                self._risky_init_order_qty, 'SWING_RISKY_INIT', position_availabe, position_availabe_reverse)
            order_params_list[0]['tag'] = 'SWING_RISKY_INIT_SELL'
            order_params_list[1]['tag'] = 'SWING_RISKY_INIT_BUY'
            for order_params in order_params_list:
                if order_params['qty'] > 0:
                    risky_init_order = AdaptiveOrder(
                        contract=self.contract,
                        buy_or_sell=order_params['action'],
                        direction=order_params['direction'],
                        order_qty=order_params['qty'],
                        order_price=order_params['price'],
                        order_tag=order_params['tag'],
                        retry_step=self.RISKY_INIT_RETRY_STEP,
                        patient_max_retry=self.RISKY_INIT_PATIENT_MAX_RETRY,
                        accelerated_max_retry=self.RISKY_INIT_ACCELERATED_MAX_RETRY,
                        max_slippage=self.RISKY_INIT_MAX_SLIPPAGE)
                    self._risky_init_orders.append(risky_init_order)
                    self.logger.debug("SWING_RISKY_INIT: Risky Init order created: {}".format(risky_init_order))

        # Run RISKY_INIT order
        order_finished = []
        for risky_init_order in self._risky_init_orders:
            order_finished.append(self.run_adaptive_order(risky_init_order))
            self.logger.debug("SWING_RISKY_INIT: Risky Init order run: {}".format(risky_init_order))
        self.logger.debug("SWING_RISKY_INIT: Risky Init order finished = {}".format(order_finished))

        # RISKY_INIT finishes
        if all(order_finished):
            self._risky_cut_qty = 0
            self._risky_cut_price = 0.0
            for risky_init_order in self._risky_init_orders:
                self._risky_cut_price = (self._risky_cut_price * self._risky_cut_qty +
                                         risky_init_order.filled_price * risky_init_order.filled_qty) / (
                                             self._risky_cut_qty + risky_init_order.filled_qty)
                self._risky_cut_qty += risky_init_order.filled_qty
            self._risky_cut_price = round(
                round(self._risky_cut_price / self.contract.tick) * self.contract.tick, self.contract.decimal)
            self._state = self.SWING_RISKY_OSC
            self._risky_init_order_qty = 0
            self._risky_init_orders = []
            self.logger.debug("SWING_RISKY_INIT: Finished. cut_qty={} cut_price={}".format(
                self._risky_cut_qty, self._risky_cut_price))
            self.logger.debug("SWING_RISKY_INIT -> SWING_RISKY_OSC")

    def _swing_risky_osc_run(self):
        # Initialize RISKY_OSC zone
        if self._risky_osc_zone is None:
            low_bound = self._risky_cut_price - (1 - self._long_short) * self.ph * self.N_GRIDS
            qa = [
                int(round(self._risky_cut_qty * self.RISKY_OSC_BUY_BACK_QTY_RATIO)),
                int(round(self._risky_cut_qty * self.RISKY_OSC_SELL_OFF_QTY_RATIO))
            ]
            qa_long, qa_short = qa[self._long_short], qa[1 - self._long_short]
            pos_qty_after_cut = self._position_qty[0] - self._position_qty[1]
            self._risky_osc_zone = GridOsc(
                logger=self.logger,
                tag='RISKY_OSC',
                contract=self.contract,
                low_bound=low_bound,
                n_grids=self.N_GRIDS,
                grid_height=self.ph,
                low_ext=True,
                high_ext=True,
                trail_amt=self.pt,
                qty_base_long=qa_long,
                qty_base_short=qa_short,
                qty_offset_long=0,
                qty_offset_short=0,
                last_order_price=self._risky_cut_price,
                k_init=0,
                qty_base_scaling=False,
                position_qty_cap_min=(pos_qty_after_cut, -self._risky_base_qty)[self._long_short],
                position_qty_cap_max=(self._risky_base_qty, pos_qty_after_cut)[self._long_short])
            self.logger.debug("SWING_RISKY_OSC _risky_osc_zone created:\n{}".format(self._risky_osc_zone))

        # Run RISKY zone
        self._risky_osc_zone.on_tick_update(self.contract.last)
        self.logger.debug("SWING_RISKY_OSC _risky_osc_zone on_tick_update:\n{}".format(self._risky_osc_zone))
        position_available = [
            self.portfolio_obj.get_traded_qty(self.account_id, self.contract.instrument_id, direction, real_time=False)
            for direction in (DIRECTION_LONG, DIRECTION_SHORT)
        ]
        order_params_list, _, _ = self._risky_osc_zone.on_tick_trade(self.contract.last, position_available[0],
                                                                     position_available[1])
        self.logger.debug("SWING_RISKY_OSC order_params_list: {}".format(order_params_list))
        self.send_limit_order(order_params_list)

        # Cancel OSC orders that are far away from current price
        orders_to_cancel = []
        for order in self.order_dict.values():
            if abs(self.contract.last - order.price) > self.N_GRIDS_CANCEL_ORDER * self.ph:
                orders_to_cancel.append(order.order_id)
        if orders_to_cancel:
            self.cancel_orders(orders_to_cancel)
            self.logger.debug("SWING_RISKY_OSC orders_to_cancel: {}".format(orders_to_cancel))

    def _swing_stop_run(self):
        # Initialize stop orders
        if not self._stop_orders:
            for direction in (0, 1):
                if self._position_qty[direction] > 0:
                    stop_order = AdaptiveOrder(
                        contract=self.contract,
                        buy_or_sell=SELL,
                        direction=(DIRECTION_LONG, DIRECTION_SHORT)[direction],
                        order_qty=self._position_qty[direction],
                        order_price=self.contract.last,
                        order_tag='SWING_STOP_' + ('long', 'short')[direction],
                        retry_step=self.STOP_RETRY_STEP,
                        patient_max_retry=self.STOP_PATIENT_MAX_RETRY,
                        accelerated_max_retry=self.STOP_ACCELERATED_MAX_RETRY,
                        max_slippage=self.STOP_MAX_SLIPPAGE)
                    self._stop_orders.append(stop_order)
                    self.logger.debug("SWING_STOP: Exit stop order created: {}".format(stop_order))

        # Run stop orders
        order_finished = []
        for stop_order in self._stop_orders:
            order_finished.append(self.run_adaptive_order(stop_order))
            self.logger.debug("SWING_STOP: Stop order is run: {}".format(stop_order))
        self.logger.debug("SWING_STOP: Stop order finished = {}".format(order_finished))

        # Stop finishes
        if all(order_finished):
            self._stop_orders = []
            self._state = self.SWING_FINISH
            self.logger.debug("SWING_STOP -> SWING_FINISH")

    def strategy_rules_on_tick(self, event):
        """
        Run strategy rules after standard on tick rules.
        :param event: StrategyEvent of EVENT_MARKETDATA.
        :return: None
        """
        # This strategy needs valid last traded price
        if PRICE not in event.even_param_ or not isinstance(event.even_param_[PRICE], (int, float)):
            return

        self.logger.debug(
            "SWING On Tick: last={} state={} long_short={} state_cleanup={} next_state={} position_qty={} cma_price={}"
            " nlv={} gain={} order_dict={} trade_dict={}".format(
                self.contract.last, self._state, self._long_short, self._state_cleanup, self._next_state_after_cleanup,
                self._position_qty, self._cma_price, self._nlv, self._gain, self.order_dict, self.trade_dict))

        # Start up
        if self._state == self.SWING_START and not self._swing_start_run():
            return

        # State transitions
        state_blocked = False
        if self._state == self.SWING_GRID_OSC:
            state_blocked = self._swing_grid_osc_transition()
        elif self._state == self.SWING_RISKY_OSC:
            state_blocked = self._swing_risky_osc_transition()
        if state_blocked:  # State cleanup in progress. Do not run any trading logic.
            return

        # State running
        if self._state == self.SWING_GRID_OSC:
            self._swing_grid_osc_run()

        elif self._state == self.SWING_REVERSAL:
            self._swing_reversal_run()

        elif self._state == self.SWING_RISKY_INIT:
            self._swing_risky_init_run()

        elif self._state == self.SWING_RISKY_OSC:
            self._swing_risky_osc_run()

        elif self._state == self.SWING_STOP:
            self._swing_stop_run()

        elif self._state == self.SWING_FINISH:
            self.thread_lock.acquire()
            self.active = False
            self.thread_lock.release()
            self.logger.info("SWING deactivated.")

    def strategy_rules_on_buy_success(self, order_ids):
        """
        Run strategy rules when buy action is successful.
        :param order_ids: List of successfully submitted order ids.
        """
        for order_id in order_ids:
            order = self.order_dict[order_id]

            if self._state == self.SWING_GRID_OSC:
                self._zones[order.tag].on_buy_sell_success(order.price)

            elif self._state == self.SWING_REVERSAL:
                for reversal_order in self._reversal_orders:
                    if reversal_order.order_tag == order.tag:
                        reversal_order.on_buysell_success(order_id, order.price)
                        break

            elif self._state == self.SWING_RISKY_INIT:
                for risky_init_order in self._risky_init_orders:
                    if risky_init_order.order_tag == order.tag:
                        risky_init_order.on_buysell_success(order_id, order.price)
                        break

            elif self._state == self.SWING_RISKY_OSC:
                self._risky_osc_zone.on_buy_sell_success(order.price)

            elif self._state == self.SWING_STOP:
                for stop_order in self._stop_orders:
                    if stop_order.order_tag == order.tag:
                        stop_order.on_buysell_success(order_id, order.price)
                        break

            elif self._state == self.SWING_FINISH:
                pass

    def strategy_rules_on_buy_fail(self, order_tag):
        """
        Run strategy rules when buy action fails.
        :param order_tag: TAG field string sent with the failed order request.
        """
        if self._state == self.SWING_GRID_OSC:
            self._zones[order_tag].on_buy_sell_fail()

        elif self._state == self.SWING_REVERSAL:
            for reversal_order in self._reversal_orders:
                if reversal_order.order_tag == order_tag:
                    reversal_order.on_buysell_fail()
                    break

        elif self._state == self.SWING_RISKY_INIT:
            for risky_init_order in self._risky_init_orders:
                if risky_init_order.order_tag == order_tag:
                    risky_init_order.on_buysell_fail()
                    break

        elif self._state == self.SWING_RISKY_OSC:
            self._risky_osc_zone.on_buy_sell_fail()

        elif self._state == self.SWING_STOP:
            for stop_order in self._stop_orders:
                if stop_order.order_tag == order_tag:
                    stop_order.on_buysell_fail()
                    break

        elif self._state == self.SWING_FINISH:
            pass

    def strategy_rules_on_sell_success(self, order_ids):
        """
        Run strategy rules when sell action is successful.
        :param order_ids: List of successfully submitted order ids.
        """
        self.strategy_rules_on_buy_success(order_ids)

    def strategy_rules_on_sell_fail(self, order_tag):
        """
        Run strategy rules when sell action fails.
        :param order_tag: TAG field string sent with the failed order request.
        """
        self.strategy_rules_on_buy_fail(order_tag)

    def strategy_rules_on_trade_update(self, order_id, trade_id):
        """
        Run strategy rules after standard trade update.
        :param order_id: int. Order id for the trade.
        :param trade_id: int. Trade id for the trade.
        :return: None
        """
        order = self.order_dict[order_id]
        trade = self.trade_dict[trade_id]

        if self._state == self.SWING_GRID_OSC:
            self._zones[order.tag].on_trade_update(order.buy_sell, order.long_short, trade.price, trade.qty)

        elif self._state == self.SWING_REVERSAL:
            for reversal_order in self._reversal_orders:
                if order_id == reversal_order.last_order_id:
                    reversal_order.on_trade_update(trade.price, trade.qty)
                    break

        elif self._state == self.SWING_RISKY_INIT:
            for risky_init_order in self._risky_init_orders:
                if order_id == risky_init_order.last_order_id:
                    risky_init_order.on_trade_update(trade.price, trade.qty)
                    break

        elif self._state == self.SWING_RISKY_OSC:
            self._risky_osc_zone.on_trade_update(order.buy_sell, order.long_short, trade.price, trade.qty)

        elif self._state == self.SWING_STOP:
            for stop_order in self._stop_orders:
                if order_id == stop_order.last_order_id:
                    stop_order.on_trade_update(trade.price, trade.qty)
                    break

        elif self._state == self.SWING_FINISH:
            pass

    def strategy_rules_on_order_status(self, order_id, order_status):
        """
        Run strategy rules after standard order status update.
        :param order_id: int. Order id.
        :param order_status: str. Order status.
        :return: None
        """
        if self._state == self.SWING_GRID_OSC:
            pass

        elif self._state == self.SWING_REVERSAL:
            for reversal_order in self._reversal_orders:
                if order_id == reversal_order.last_order_id:
                    reversal_order.on_order_status(order_status)
                    break

        elif self._state == self.SWING_RISKY_INIT:
            for risky_init_order in self._risky_init_orders:
                if order_id == risky_init_order.last_order_id:
                    risky_init_order.on_order_status(order_status)
                    break

        elif self._state == self.SWING_RISKY_OSC:
            pass

        elif self._state == self.SWING_STOP:
            for stop_order in self._stop_orders:
                if order_id == stop_order.last_order_id:
                    stop_order.on_order_status(order_status)
                    break

        elif self._state == self.SWING_FINISH:
            pass
