# Trading robot

Trading bot to trade using python-binance API on Binance testnet.

## Requirements:
* python 3.8
* python-binance
* inputimeout
* pmdarima
* statsmodels
* jsonschema

# config.json

This file is used to config robot. First are api key and secret to connnect to binance testnet. Timeout means how much seconds to wait between trying to trade pairs. Interval is used to retrieve klines/candlestick data. Long term and short term properties are used to determine what period to use for calculating moving averages.

### Example JSON config file

```JSON
{
  "api_key": "api_key",
  "api_secret": "api_secret",
  "timeout": 60,
  "interval": "15m"
  "long_term": 15,
  "short_term": 5,
  "band": 0.001
}
```
# pairs.json

This file holds symbols data for trading. There can be `limit` or `market` type orders. If limit type is chosen, `time_in_force` must be provided (FOK - fill or kill, GTC - good till canceled, IOC - immediate or cancel). Trade quantity describes how much base asset is traded each trade.

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
