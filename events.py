"""
Definition of events.
"""


from abc import ABC


EVENT_LOG = 'eLog'                          #Log Event
EVENT_MARKETDATA = 'eMarketData'           #Pushing MarketData Event
EVENT_TRADE = 'eTrade'                      #Trade Event
EVENT_BUY = 'eBuy'                          #Buy Event
EVENT_SELL = 'eSell'                        #Sell Event
EVENT_CANCEL = 'eCancel'                    #Cancel Event
EVENT_POSITION = 'ePosition'               #Position Query Event
EVENT_STATUS = 'eStatus'                   #Order Status Event
EVENT_ACCOUNT = 'eAccount'                 #Account Query Event
EVENT_PROFIT_CHANGED = 'eProfitChanged'    #Profit Event


class StrategyEvent:
    def __init__(self, type_=None, even_param_=None):
        self.type_ = type_
        self.even_param_ = even_param_

    def clear(self):
        """
        Delete unreferenced source.
        """
        self.even_param_.clear()


class EventEngine(ABC):
    pass
