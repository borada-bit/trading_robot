import json

from statistics import mean
from typing import Tuple

from jsonschema import validate
from jsonschema.exceptions import ValidationError
from inputimeout import inputimeout, TimeoutOccurred

from binance import Client, exceptions
from binance.helpers import round_step_size

from forecast import model_predict_arima
import numpy as np
import pandas as pd
from datetime import datetime


def print_menu():
    print("""
    1. Print balances.
    2. Print orders for symbol.
    3. Print symbols positions.
    4. Print order.
    5. Cancel order manually.
    6. Print symbol price filter.
    ----------------------------------
    9. Print menu.
    0. Quit.""")
    pass


CONFIG_FILE_NAME = 'config.json'
PAIRS_FILE_NAME = 'pairs.json'
RESULTS_DIR_PREFIX = 'results'
LOGGING_FILE_NAME = 'trades.log'

MENU_START_INDEX = 0
MENU_END_INDEX = 9
MENU_TRADE_INDEX = -1

KLINES_COLUMNS = ['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time',
                  'Quote Asset Volume', 'Number of Trades', 'Taker Base Volume', 'Taker Quote Volume', 'Ignore']


class Robot:
    MIN_PAIRS = 1
    MAX_PAIRS = 5

    def __init__(self):
        with open(CONFIG_FILE_NAME, 'r') as config_file:
            data = json.load(config_file)
            validate(instance=data, schema=config_schema)
            self._client = Client(data['api_key'], data['api_secret'], testnet=True)
            self._long_term = data['long_term']
            self._short_term = data['short_term']
            if self._short_term >= self._long_term:
                raise ValidationError(message="Short term should be lower than long term!")
            self._timeout = data['timeout']
            self._interval = data['interval']

        with open(PAIRS_FILE_NAME, 'r') as pairs_file:
            data = json.load(pairs_file)
            validate(instance=data, schema=pairs_schema)
            self._pairs_config = data

        self._pairs_data = {key: {} for key in self._pairs_config}
        for symbol in self._pairs_data.keys():
            self._pairs_data[symbol]['tick_size'] = self._get_ticksize(symbol)
            self._pairs_data[symbol]['long_sma'] = None
            self._pairs_data[symbol]['short_sma'] = None
            self._pairs_data[symbol]['price_list'] = []
            self._pairs_data[symbol]['df'] = pd.DataFrame
            self._pairs_data[symbol]['arima_forecast'] = 0
            log_file = open(f"{RESULTS_DIR_PREFIX}/{symbol}/{LOGGING_FILE_NAME}", "w")
            log_file.write("timestamp, order_type, quantity, price\n")

    def run(self) -> None:
        self._get_historic_prices(limit=self._long_term)
        self._get_klines_as_df(limit=1000)
        self._calculate_arima()
        self._calculate_sma()
        print_menu()
        quit_loop = False
        while not quit_loop:
            choice = self._get_choice()

            if choice == 0:
                self._save_pairs_data()
                quit_loop = True
            elif choice == 1:
                self._print_balances()
            elif choice == 2:
                self._print_symbol_orders()
            elif choice == 3:
                self._print_positions()
            elif choice == 4:
                self._print_symbol_order()
            elif choice == 5:
                self._cancel_order()
            elif choice == 6:
                self._print_symbol_info()
            elif choice == 9:
                print_menu()
            elif choice == MENU_TRADE_INDEX:
                self._try_trade()
            else:
                pass
        pass

    # HELPER FUNC START
    def _calculate_sma(self) -> None:
        for symbol in self._pairs_data:
            self._pairs_data[symbol]['long_sma'] = mean(self._pairs_data[symbol]['price_list'])
            self._pairs_data[symbol]['short_sma'] = mean(self._pairs_data[symbol]['price_list'][0:self._short_term])
            print(f"{symbol} | LSMA: {self._pairs_data[symbol]['long_sma']} | SSMA {self._pairs_data[symbol]['short_sma']}")
        pass

    def _calculate_arima(self) -> None:
        for symbol in self._pairs_data:
            self._pairs_data[symbol]['arima_forecast'] = model_predict_arima(symbol, self._pairs_data[symbol]['df'])
            print(self._pairs_data[symbol]['arima_forecast'])

    def _get_choice(self) -> int:
        try:
            user_string = inputimeout(prompt='>> ', timeout=self._timeout)
            choice = int(user_string)
            if choice < MENU_START_INDEX or choice > MENU_END_INDEX:
                raise ValueError()
        except TimeoutOccurred:
            choice = MENU_TRADE_INDEX
        except ValueError:
            print("Entered option is invalid!")
            choice = MENU_END_INDEX
        return choice

    def _try_trade(self) -> None:
        klines = 1
        self._get_historic_prices(klines)
        self._get_klines_as_df(klines)
        self._calculate_arima()
        self._calculate_sma()
        self._check_opportunity()
        pass

    # strategy
    def _check_opportunity(self) -> None:
        # add configuration what to trade with (sma lma, ARIMA, random?)
        for symbol, config in self._pairs_config.items():
            position = config['position']
            long_sma = self._pairs_data[symbol]['long_sma']
            short_sma = self._pairs_data[symbol]['short_sma']
            price = None
            if config['order_type'] == Client.ORDER_TYPE_LIMIT:
                price = self._get_symbol_avg_price(symbol)
                if self._pairs_data[symbol]['arima_forecast'] > price and position == 'BUY':
                    if self._make_order(symbol, position, config['trade_quantity'], price):
                        config['position'] = 'SELL'
                elif self._pairs_data[symbol]['arima_forecast'] < price and position == 'SELL':
                    if self._make_order(symbol, position, config['trade_quantity'], price):
                        config['position'] = 'BUY'

            if short_sma > long_sma and position == 'BUY':
                if self._make_order(symbol, position, config['trade_quantity'], price):
                    config['position'] = 'SELL'
            elif short_sma < long_sma and position == 'SELL':
                if self._make_order(symbol, position, config['trade_quantity'], price):
                    config['position'] = 'BUY'

    pass

    # Log trade details
    def _log_trade(self, symbol: str, order_type: str, quantity: float, price: float) -> None:
        log_file = open(f"{RESULTS_DIR_PREFIX}/{symbol}/{LOGGING_FILE_NAME}", "a")
        log_file.write(f"{datetime.now()}, {order_type}, {quantity}, {price}\n")
        log_file.close()

    # HELPER FUNC END

    # GETTERS START
    def _get_historic_prices(self, limit: int) -> None:
        """
        Retrieve and store the historical close prices of each symbol from the client.

        Args:
        limit: An integer representing the number of historical price data points to retrieve.

        Returns:
        None
        """
        close_price_index = 4
        for symbol in self._pairs_data:
            klines = self._client.get_historical_klines(symbol, self._interval, limit=limit)
            if self._pairs_data[symbol]['price_list']:
                self._pairs_data[symbol]['price_list'].pop()
            for kline in klines:
                self._pairs_data[symbol]['price_list'].insert(0, float(kline[close_price_index]))
            print(f"{symbol} recent prices {self._pairs_data[symbol]['price_list'][:4]} past prices {self._pairs_data[symbol]['price_list'][-4:]}")
        pass

    def _get_klines_as_df(self, limit: int) -> None:
        for symbol in self._pairs_data:
            klines = self._client.get_historical_klines(symbol, self._interval, limit=limit)
            klines = np.array(klines)
            df = pd.DataFrame(klines.reshape(-1, 12), dtype=float, columns=KLINES_COLUMNS)
            df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
            # TAIL - recent prices, HEAD - old prices
            df = df[['Open Time', 'Close']]
            if self._pairs_data[symbol]['df'].empty:
                self._pairs_data[symbol]['df'] = df
            else:
                # remove first element - oldest price
                self._pairs_data[symbol]['df'] = self._pairs_data[symbol]['df'].iloc[1:]
                # print(f"before append {self._pairs_data[symbol]['df']}")
                # append neweset price to the end
                self._pairs_data[symbol]['df'] = pd.concat([self._pairs_data[symbol]['df'], df],
                                                           ignore_index=True)
                # print(f"after append {self._pairs_data[symbol]['df']}")
            # print(f"{symbol} recent prices {self._pairs_data[symbol]['df'].tail(4)['Close'].values} past prices {self._pairs_data[symbol]['df'].head(4)['Close'].values}")
        pass

    def _get_symbol_orders(self, symbol) -> dict:
        return self._client.get_all_orders(symbol=symbol)

    def _get_account_balances(self) -> list:
        return self._client.get_account()['balances']

    def _get_symbol_avg_price(self, symbol: str) -> float:
        symbol_avg_price = float(self._client.get_avg_price(symbol=symbol)['price'])
        return round_step_size(symbol_avg_price, self._pairs_data[symbol]['tick_size'])

    def _get_symbol_order(self, symbol: str, orderId: str) -> dict:
        return self._client.get_order(symbol=symbol, orderId=orderId)

    def _get_ticksize(self, symbol) -> float:
        price_filter_index = 0
        symbol_filters = self._client.get_symbol_info(symbol=symbol)['filters']
        return float(symbol_filters[price_filter_index]['tickSize'])

    def _get_symbol_info(self, symbol) -> dict:
        return self._client.get_symbol_info(symbol=symbol)

    def _get_asset_value(self, asset_dict) -> Tuple[float, float]:
        default_amounts = {'BNB': 1000.0,
                           'BTC': 1.0,
                           'BUSD': 10000.0,
                           'ETH': 100.0,
                           'LTC': 500.0,
                           'TRX': 500000.0,
                           'USDT': 10000.0,
                           'XRP': 50000.0}

        if asset_dict['asset'] in ['BUSD', 'USDT']:
            return float(asset_dict['free']), default_amounts[asset_dict['asset']]
        else:
            ticker = self._client.get_ticker(symbol=asset_dict['asset'] + "BUSD")
            price = float(ticker['lastPrice'])
            return float(asset_dict['free']) * price, default_amounts[asset_dict['asset']] * price

    # GETTERS END

    # OTHER API CALLS START
    def _cancel_symbol_order(self, symbol: str, orderId: str) -> dict:
        return self._client.cancel_order(symbol=symbol, orderId=orderId)

    # makes order at given price and returns result if successful or not
    def _make_order(self, symbol: str, side: str, qty: float, price: float = None) -> bool:
        order_completed = False
        try:
            response = self._client.create_order(
                symbol=symbol,
                side=side,
                type=self._pairs_config[symbol]['order_type'],
                quantity=qty,
                price=price,
                timeInForce=self._pairs_config[symbol]['time_in_force'],
            )
            # TODO: make logging?
            print(f"{response['side']} {response['type']} {response['symbol']} {response['status']}")
            if response['status'] == Client.ORDER_STATUS_FILLED:
                order_completed = True
                self._log_trade(symbol, side, qty, price)
        except exceptions.BinanceOrderException as e:
            print(e.message)
        return order_completed

    # OTHER API CALLS END

    # MENU OPTIONS START
    def _save_pairs_data(self) -> None:
        validate(instance=self._pairs_config, schema=pairs_schema)
        with open(PAIRS_FILE_NAME, 'w') as pairs_file:
            json.dump(self._pairs_config, pairs_file, indent=2, separators=(',', ': '))
        pass

    def _print_balances(self) -> None:
        balances = self._get_account_balances()
        asset_values = {}
        asset_default_values = {}
        if balances:
            for asset in balances:
                print(asset)
                try:
                    value, default_value = self._get_asset_value(asset)
                    asset_values[asset['asset']] = value
                    asset_default_values[asset['asset']] = default_value
                except exceptions.BinanceAPIException as e:
                    print(f"Error while fetching value for {asset['asset']}: {e}")
                    continue

        total_value = sum(asset_values.values())
        print(f"Total value: {total_value} BUSD")
        total_default_value = sum(asset_default_values.values())
        print(f"Total default value: {total_default_value}")
        print(f"Difference {(total_value - total_default_value):.2f} BUSD")
        pass

    def _print_positions(self) -> None:
        for key, value in self._pairs_config.items():
            print(f"{key} position: {value['position']}")
        pass

    def _print_symbol_orders(self) -> None:
        symbol = input("Enter symbol: ")
        last_n_items = 5
        orders = self._get_symbol_orders(symbol=symbol)
        if orders:
            orders = orders[-last_n_items:]
            for order in orders:
                print(f"id:{order['orderId']} price:{order['price']} "
                      f"side:{order['side']} executed:{order['executedQty']}")
        pass

    def _print_symbol_order(self) -> None:
        symbol = input("Enter symbol: ")
        orderId = input("order id:")
        order = self._get_symbol_order(symbol, orderId)
        print(order)
        pass

    def _cancel_order(self) -> None:
        symbol = input("Enter symbol: ")
        orderId = input("order id")
        result = self._cancel_symbol_order(symbol, orderId)
        print(result)
        pass

    def _print_symbol_info(self):
        symbol = input("Enter symbol: ")
        symbol_info = self._get_symbol_info(symbol)
        print(f"{symbol_info['filters'][0]}")
    # MENU OPTIONS END


config_schema = {
    "type": "object",
    "required": ["api_key", "api_secret", "timeout", "long_term", "short_term", "interval"],
    "properties": {
        "api_key": {"type": "string"},
        "api_secret": {"type": "string"},
        # how often to check for trades
        "timeout": {"type": "integer", "minimum": 60, "maximum": 3600},
        # from python-binance source code, these are enums used for kline intervals
        "interval": {"enum": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M"]},
        # how many data points to take from given interval
        "long_term": {"type": "integer", "minimum": 15},
        "short_term": {"type": "integer", "minimum": 5}
    },
    "additionalProperties": False
}

pairs_schema = {
    "type": "object",
    "minProperties": 1,
    "maxProperties": 5,
    "patternProperties": {
        "^[A-Z]+$": {
            "required": [
                "trade_quantity",
                "position",
                "order_type",
                "time_in_force"
            ],
            "type": "object",
            "properties": {
                "trade_quantity": {
                    "type": "number"
                },
                "position": {
                    "enum": [
                        "BUY",
                        "SELL"
                    ]
                },
                "order_type": {
                    "enum": [
                        "MARKET",
                        "LIMIT"
                    ]
                },
                "time_in_force": {
                    "enum": [
                        "FOK",
                        "GTC",
                        "IOC",
                        None
                    ]
                }
            },
            "if": {
                "properties": {
                    "order_type": {
                        "enum": [
                            "LIMIT"
                        ]
                    }
                }
            },
            "then": {
                "properties": {
                    "time_in_force": {
                        "enum": [
                            "FOK",
                            "GTC",
                            "IOC"
                        ]
                    }
                }
            },
            "else": {
                "properties": {
                    "time_in_force": {
                        "enum": [
                            None
                        ]
                    }
                }
            },
            "additionalProperties": False
        }
    },
    "additionalProperties": False
}
