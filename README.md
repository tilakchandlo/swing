# Swing Trading

### An automatic swing trading strategy implementation.

## Features

* Automatically reverse positions while market price swings in a pre-defined range.
* Swing range is split into price zones to gradually increase or decrease holding positions to reduce risk and smooth out capital usage.
* Grid-based oscillatory trading in each price zone by trailing stop.
* Advanced adaptive order type reduces timing risk with 4 excecution modes: `PATIENT, ACCELERATED, URGENT, PANIC`, used for long/short
reversal, stop loss and profit taking.
* Automatic stop for loss cut or profit taking.

<p align='center'><img src="doc/state_flowchart.png" width=480></p>

## Documentation
### Jupyter Notebook: [swing_trade.ipynb](https://nbviewer.jupyter.org/github/0liu/swing_trading/blob/master/doc/swing_trade.ipynb)