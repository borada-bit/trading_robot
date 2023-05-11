import json

from statistics import mean
from typing import Tuple

from jsonschema import validate
from jsonschema.exceptions import ValidationError
from inputimeout import inputimeout, TimeoutOccurred

from binance import Client, exceptions
from binance.helpers import round_step_size

from forecast import model_predict_arima
from util import graph_orders
import numpy as np
import pandas as pd
import time


def print_menu():
    print("""
    1. Print balances.
    2. Print orders for symbol.
    3. Print symbols positions.
    4. Print order.
    5. Cancel order manually.
    6. Print symbol price filter.
    7. Graph symbol orders.
    ----------------------------------
    9. Print menu.
    0. Quit.""")
    pass


CONFIG_FILE_NAME = 'config.json'
PAIRS_FILE_NAME = 'pairs.json'

MIN_MENU_TIMEOUT = 60
MAX_MENU_TIMEOUT = 3600

ORDER_RETRY_WAIT_TIME = 10
ORDER_MAX_RETRIES = 3

MIN_LONG_TERM_SMA = 15
MIN_SHORT_TERM_SMA = 5
MIN_LONG_TERM_BAND = 0
MAX_LONG_TERM_BAND = 0.1  # 10 percent
MIN_ENTRY_TRESHOLD = 1
MAX_ENTRY_TRESHOLD = 3
MIN_EXIT_TRESHOLD = 0.1
MAX_EXIT_TRESHOLD = 1

MENU_START_INDEX = 0
MENU_END_INDEX = 9
MENU_TRADE_INDEX = -1

KLINES_COLUMNS = ['Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close Time',
                  'Quote Asset Volume', 'Number of Trades', 'Taker Base Volume', 'Taker Quote Volume', 'Ignore']

# Follow the trend and forecast next prices using ARIMA
TENDENCY_STRATEGY = 'TENDENCY_ARIMA'
# Expecting that price will return to the mean using long SMA and short SMA
MEAN_STRATEGY = 'MEAN_SMA'
# Pairs trading
PT_STRATEGY = 'PT_STRATEGY'


class Robot:
    MIN_PAIRS = 1
    MAX_PAIRS = 5

    def __init__(self):
        with open(CONFIG_FILE_NAME, 'r') as config_file:
            data = json.load(config_file)
            validate(instance=data, schema=config_schema)
            self._client = Client(data['api_key'], data['api_secret'], testnet=True)
            self._strategy = data['strategy']
            if self._strategy == MEAN_STRATEGY:
                self._long_term = data['long_term']
                self._short_term = data['short_term']
                self._band = data['band']
                if self._short_term >= self._long_term:
                    raise ValidationError(message="Short term should be lower than long term!")
            elif self._strategy == PT_STRATEGY:
                self._entry_treshold_ratio = data['entry_treshold']
                self._exit_treshold_ratio = data['exit_treshold']
                if self._exit_treshold_ratio >= self._entry_treshold_ratio:
                    raise ValidationError(message="Exit treshold should be lower than entry treshold!")
            self._timeout = data['timeout']
            self._interval = data['interval']

        with open(PAIRS_FILE_NAME, 'r') as pairs_file:
            data = json.load(pairs_file)
            validate(instance=data, schema=pairs_schema)
            self._pairs_config = data

        self._trading_pairs = self._pairs_config["pairs"]
        symbols = set()
        for pair in self._trading_pairs:
            for symbol in pair.values():
                symbols.add(symbol)
            pair['spread'] = pd.DataFrame
            pair['mean'] = 0
            pair['std'] = 0
        self._pairs_data = {key: {} for key in self._pairs_config if key != "pairs" and key in symbols}

        for symbol in self._pairs_data.keys():
            self._pairs_data[symbol]['tick_size'] = self._get_ticksize(symbol)
            if self._strategy == MEAN_STRATEGY:
                self._pairs_data[symbol]['long_sma'] = None
                self._pairs_data[symbol]['short_sma'] = None
                self._pairs_data[symbol]['long_band'] = None
                self._pairs_data[symbol]['price_list'] = []
            elif self._strategy == TENDENCY_STRATEGY:
                self._pairs_data[symbol]['df'] = pd.DataFrame
                self._pairs_data[symbol]['arima_forecast'] = 0
            elif self._strategy == PT_STRATEGY:
                self._pairs_data[symbol]['df'] = pd.DataFrame

    def run(self) -> None:
        if self._strategy == MEAN_STRATEGY:
            self._get_historic_prices(limit=self._long_term)
            self._calculate_sma()
        elif self._strategy == TENDENCY_STRATEGY:
            self._get_klines_as_df(limit=1000)
            self._calculate_arima()

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
            elif choice == 7:
                self._graph_symbol_orders()
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
            self._pairs_data[symbol]['long_band'] = self._pairs_data[symbol]['long_sma'] * self._band
        pass

    def _calculate_arima(self) -> None:
        for symbol in self._pairs_data:
            self._pairs_data[symbol]['arima_forecast'] = model_predict_arima(symbol, self._pairs_data[symbol]['df'])
        pass

    def _calculate_spread(self) -> None:
        for pair in self._trading_pairs:
            # setting open time as index is importante!
            asset1_data = self._pairs_data[pair['asset1']]['df'].set_index('Open Time')
            asset2_data = self._pairs_data[pair['asset2']]['df'].set_index('Open Time')

            print(f'Current symbols :{pair["asset1"]} and {pair["asset2"]}')
            asset1_returns = (asset1_data['Close'].diff().dropna()).to_frame()
            asset2_returns = (asset2_data['Close'].diff().dropna()).to_frame()

            asset1_returns.columns.values[0] = 'return'
            asset2_returns.columns.values[0] = 'return'

            spread = (asset1_returns['return'] - asset2_returns['return']).to_frame()
            spread.columns.values[0] = 'return'
            pair['mean'] = spread["return"].mean()
            pair['std'] = spread["return"].std()
            pair['spread'] = spread
        pass

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
        if self._strategy == MEAN_STRATEGY:
            self._get_historic_prices(klines)
            self._calculate_sma()
            self._trade_sma()
        elif self._strategy == TENDENCY_STRATEGY:
            self._get_klines_as_df(klines)
            self._calculate_arima()
            self._trade_arima()
        elif self._strategy == PT_STRATEGY:
            self._get_klines_as_df(klines)
            self._calculate_spread()
            self._trade_pairs()
        pass

    def _trade_sma(self) -> None:
        for symbol, config in self._pairs_config.items():
            position = config['position']
            long_sma = self._pairs_data[symbol]['long_sma']
            short_sma = self._pairs_data[symbol]['short_sma']
            band = self._pairs_data[symbol]['long_band']
            price = None
            if config['order_type'] == Client.ORDER_TYPE_LIMIT:
                price = self._get_symbol_avg_price(symbol)
            print(f"Trying to trade {symbol=} {position=} {price=} {long_sma=} {short_sma=}")
            if short_sma > (long_sma + band) and position == 'BUY':
                if self._make_order(symbol, position, config['trade_quantity'], price):
                    config['position'] = 'SELL'
            elif short_sma < (long_sma + band) and position == 'SELL':
                if self._make_order(symbol, position, config['trade_quantity'], price):
                    config['position'] = 'BUY'
        pass

    def _trade_arima(self) -> None:
        for symbol, config in self._pairs_config.items():
            position = config['position']
            price = self._get_symbol_avg_price(symbol)
            if self._pairs_data[symbol]['arima_forecast'] > price and position == 'BUY':
                if self._make_order(symbol, position, config['trade_quantity'], price):
                    config['position'] = 'SELL'
            elif self._pairs_data[symbol]['arima_forecast'] < price and position == 'SELL':
                if self._make_order(symbol, position, config['trade_quantity'], price):
                    config['position'] = 'BUY'
        pass

    def _trade_pairs(self) -> None:
        for pair in self._trading_pairs:
            # Compute current distance
            # current_distance = btc_returns.iloc[i] - eth_returns.iloc[i]
            print(f"current distance is {pair['spread']['return'].iloc[-1]} mean:{pair['mean']} std:{pair['std']}")

            current_distance = pair['spread']['return'].iloc[-1]
            # Check if we should enter a position
            entry_threshold = pair['std'] * self._entry_treshold_ratio
            exit_threshold = pair['std'] * self._exit_treshold_ratio
            if current_distance > pair['mean'] + entry_threshold:
                btc_position = 1
                eth_position = -1
            elif current_distance < pair['mean'] - entry_threshold:
                btc_position = -1
                eth_position = 1
            # Check if we should exit a position
            elif abs(current_distance) < exit_threshold:
                btc_position = 0
                eth_position = 0
                pass
        pass
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
                # append neweset price to the end
                self._pairs_data[symbol]['df'] = pd.concat([self._pairs_data[symbol]['df'], df],
                                                           ignore_index=True)
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

    # Makes order at given price and returns result if successful or not
    def _make_order(self, symbol: str, side: str, qty: float, price: float = None) -> bool:
        # Retry is useful if order type is LIMIT
        retries = 0
        order_completed = False
        while not order_completed and retries < ORDER_MAX_RETRIES:
            try:
                response = self._client.create_order(
                    symbol=symbol,
                    side=side,
                    type=self._pairs_config[symbol]['order_type'],
                    quantity=qty,
                    price=price,
                    timeInForce=self._pairs_config[symbol]['time_in_force'],
                )
                print(f"{response['side']} {response['type']} {response['symbol']} {response['status']}")
                if response['status'] == Client.ORDER_STATUS_FILLED:
                    order_completed = True
                    break
            except exceptions.BinanceOrderException as e:
                print(e.message)
            retries += 1
            time.sleep(ORDER_RETRY_WAIT_TIME)
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

    def _print_symbol_info(self) -> None:
        symbol = input("Enter symbol: ")
        symbol_info = self._get_symbol_info(symbol)
        print(f"{symbol_info['filters'][0]}")

    def _graph_symbol_orders(self) -> None:
        for symbol in self._pairs_data:
            orders = self._get_symbol_orders(symbol=symbol)
            orders_filtered = [
                {'time': order['time'], 'price': float(order['price']),
                 'side': order['side'], 'executed': float(order['executedQty'])} for order in orders]
            orders_df = pd.DataFrame(orders_filtered, columns=['time', 'price', 'side', 'executed'])

            start_str = str(orders_df['time'].iloc[0])
            end_str = str(orders_df['time'].iloc[-1])

            klines = self._client.get_historical_klines(symbol, self._interval, start_str=start_str, end_str=end_str)
            klines = np.array(klines)
            prices_df = pd.DataFrame(klines.reshape(-1, 12), dtype=float, columns=KLINES_COLUMNS)
            prices_df['Open Time'] = pd.to_datetime(prices_df['Open Time'], unit='ms')
            prices_df = prices_df[['Open Time', 'Close']]

            graph_orders(symbol, orders_df, prices_df)

    # MENU OPTIONS END


config_schema = {
    "type": "object",
    "required": ["api_key", "api_secret", "timeout", "interval", "strategy"],
    "properties": {
        "api_key": {"type": "string"},
        "api_secret": {"type": "string"},
        "timeout": {"type": "integer", "minimum": MIN_MENU_TIMEOUT, "maximum": MAX_MENU_TIMEOUT},
        "interval": {"enum": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M"]},
        "strategy": {
            "type": "string",
            "enum": [TENDENCY_STRATEGY, MEAN_STRATEGY]
        },
        "long_term": {
            "type": "integer",
            "minimum": MIN_LONG_TERM_SMA
        },
        "short_term": {
            "type": "integer",
            "minimum": MIN_SHORT_TERM_SMA
        },
        "band": {
            "type": "number",
            "format": "float",
            "minimum": MIN_LONG_TERM_BAND,
            "maximum": MAX_LONG_TERM_BAND
        }
    },
    "if": {
        "properties": {"strategy": {"const": "MEAN_SMA"}}
    },
    "then": {
        "required": ["long_term", "short_term", "band"]
    },
    "additionalProperties": False
}

pairs_schema = {
    "type": "object",
    "minProperties": Robot.MIN_PAIRS,
    "maxProperties": Robot.MAX_PAIRS,
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
