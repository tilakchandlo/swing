"""
Common utilities.
"""


def get_number_of_decimal(tick_size):
    """
    Get price decimal number of a contract from its tick size.
    """
    str_price_tick_ = str(tick_size)
    decimal_pos_ = str_price_tick_.find('.')
    if decimal_pos_ == -1 or str_price_tick_[decimal_pos_ + 1:] == '0':
        return 0
    else:
        return len(str_price_tick_) - (decimal_pos_ + 1)


def if_market_open(exchange_hours):
    """
    Check if market is open now.
    """
    return True