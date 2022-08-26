# Trading robot

Trading bot to trade using python-binance API on Binance testnet.

## Requirements:
* python 3.8
* python-binance
* inputimeout

# config.json

This file is used to config robot. First are api key and secret to connnect to binance testnet. Timeout means how much time to wait between trying to trade pairs provided in seconds. 60 - means try to trade every 60 seconds. Interval is used to determine what interval is used to retrieve klines/candlestick data. Long term and short term properties are used to determine what period to use for calculating moving averages, they are compared when trading.

### Example JSON config file

```JSON
{
  "api_key": "api_key",
  "api_secret": "api_secret",
  "timeout": 60,
  "interval": "15m"
  "long_term": 15,
  "short_term": 5
}
```
# pairs.json

This file holds symbols data that robot needs to trade. There can be limit or market type orders. If limit type is chosen, one must provide time_in_force parameter (FOK - fill or kill, GTC - good till canceled, IOC - immediate or cancel). Trade quantity describes how much base asset to trade with each trade.

### Example JSON pairs file

```JSON
{
  "BTCBUSD": {
    "trade_quantity": 0.01,
    "position": "BUY",
    "order_type": "LIMIT",
    "time_in_force": "FOK"
  },
  "LTCBUSD": {
    "trade_quantity": 1,
    "position": "BUY",
    "order_type": "MARKET",
    "time_in_force": null
  }
}
```
