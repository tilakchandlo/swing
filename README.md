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
<p><img src="images/grid_osc.png" width=480></p>

## Zone Switch
<p><img src="images/zone_switch.png" width=480></p>

## State Transition Implementation
<p><img src="images/state_transition.png" width=480></p>