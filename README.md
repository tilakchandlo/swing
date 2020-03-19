# Swing Trading

### An automatic swing trading strategy implementation.

## Features

* Automatically reverse positions while market price swings in a pre-defined range.
* Swing range is split into price zones to gradually increase or decrease holding positions to reduce risk and smooth out capital usage.
* Grid-based oscillatory trading in each price zone by trailing stop.
* Advanced adaptive order type reduces timing risk with 4 excecution modes: `PATIENT, ACCELERATED, URGENT, PANIC`.
* Automatic stop for loss cut or profit taking.

## Price Zone Definition and Transition
<p><img src="images/state_flowchart.png" width=480></p>

## Direction Reversal (Swing)
<p><img src="images/state_reversal.png" width=480></p>

## Grid-Based Oscillatory Trading
The oscillatory order price is based on the last successful order price as well as the trailing price from the last highest/lowest
order price, i.e.,
$$P_{last\_order} - P_{last} \geq P_h \space\space and \space\space P_{last}-P_{lowest} \geq P_t, \space\space or$$
$$P_{last} - P_{last\_order} \geq P_h \space\space and \space\space P_{highest}-P_{last} \geq P_t, \space\space or$$
The order quantity is determined by
$$Q_{order} = m*Q_a + k*Q_{offset}$$
where $m$ is the number of grids that the market traverses from $P_{last_order}$ to $P_{last}$, determined by
$$m = \lfloor \lvert P_{last} - P_{last_order} \rvert /P_h \rfloor$$
and $k$ is the oscillatory quantity offset coefficient, which increases by 1 when the accumulated profit in the current trading zone
exceeds the pre-defined threshold $G_{k\_th}$ determined by
$$G_{k\_th} = (P_H-P_L) * (N_{grids} * Q_a + k * Q_{offset}).$$
<p><img src="images/grid_osc.png" width=480></p>

## Zone Switch
Switching between the trading zones Net, Inc, Osc, Dec happens when market price crosses more than one grid of a neighbor zone,
$$ p_{last} > P_{high\_bound} + P_h \space\space or \space\space p_{last} < P_{low\_bound} - P_h .$$
<p><img src="images/zone_switch.png" width=480></p>

## State Transition Implementation
<p><img src="images/state_transition.png" width=480></p>