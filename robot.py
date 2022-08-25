import json

from statistics import mean
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from inputimeout import inputimeout, TimeoutOccurred

from binance import Client, exceptions
from binance.enums import *
from binance.helpers import round_step_size


def print_menu():
    # TODO: decide if menu is needed at all!
    print("""
    1. Print balances.
    2. Print orders for symbol.
    3. Print symbols positions.
    4. Print order.
    5. Cancel order manually.
    ----------------------------------
    9. Print menu.
    0. Quit.""")
    pass


class Robot:
    def __init__(self):
        # TODO: make file names some kind of constant
        with open("config.json", 'r') as config_file:
            data = json.load(config_file)
            validate(instance=data, schema=config_schema)
            self.client = Client(data['api_key'], data['api_secret'], testnet=True)
            self.long_term = data['long_term']
            self.short_term = data['short_term']
            if self.short_term >= self.long_term:
                raise ValidationError(message="Short term should be lower than long term!")
            self.timeout = data['timeout']
            self.interval = data['interval']
            self.order_type = data['order_type']
            self.time_in_force = data['time_in_force']

        with open('pairs.json', 'r') as pairs_file:
            data: dict = json.load(pairs_file)
            validate(instance=data, schema=pairs_schema)
            self.pairs_config = data

        self.pairs_data = {key: {} for key in self.pairs_config}
        for key in self.pairs_data.keys():
            # poh ir tiesiog visada pasiimt is serverio afdru reikes stop limit daryt?
            self.pairs_data[key]['tick_size'] = self._get_ticksize(key)
            self.pairs_data[key]['long_sma'] = None
            self.pairs_data[key]['short_sma'] = None
            self.pairs_data[key]['price_list'] = []

    def run(self) -> None:
        self._get_historic_prices(limit=self.long_term)
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
            elif choice == 9:
                print_menu()
            elif choice == -1:
                self._try_trade()
            else:
                pass
        pass

    # HELPER FUNC START
    def _calculate_sma(self) -> None:
        for i, key in enumerate(self.symbols_data.keys()):
            self.symbols_data[key]['long_sma'] = mean(self.price_list[i])
            self.symbols_data[key]['short_sma'] = mean(self.price_list[i][0:self.short_term])
        pass

    def _get_choice(self) -> int:
        try:
            user_string = inputimeout(prompt='>> ', timeout=self.timeout)
            choice = int(user_string)
            # TODO: make these constant
            if choice < 0 or choice > 9:
                raise ValueError()
            return choice
        except TimeoutOccurred:
            return -1
        except ValueError:
            print("Entered option is invalid!")
            return 9

    def _try_trade(self) -> None:
        klines = 1
        self._get_historic_prices(klines)
        self._calculate_sma()
        self._check_opportunity()
        pass

    def _check_opportunity(self) -> None:
        for key, value in self.pairs_data.items():
            # if short_sma > long_sma : buy ? sell
            position = value['position']
            long_sma = self.symbols_data[key]['long_sma']
            short_sma = self.symbols_data[key]['short_sma']
            # TODO: check if qty is valid depending on price filter and etc.
            if short_sma > long_sma and position == 'BUY':
                if self._make_order(key, position, value['trade_quantity']):
                    # TODO: check if this change object data instead of local variable
                    value['position'] = 'SELL'
            elif short_sma < long_sma and position == 'SELL':
                if self._make_order(key, position, value['trade_quantity']):
                    value['position'] = 'BUY'
        pass

    # HELPER FUNC END

    # GETTERS START
    def _get_historic_prices(self, limit: int) -> None:
        close_price_index = 4
        try:
            for i, symbol in enumerate(self.pairs_data):
                klines = self.client.get_historical_klines(symbol, self.interval, limit=limit)
                if self.price_list[i]:
                    self.price_list[i].pop()
                for kline in klines:
                    self.price_list[i].insert(0, float(kline[close_price_index]))
        except exceptions.BinanceAPIException as e:
            print(e.message)
        pass

    def _get_symbol_orders(self, symbol) -> dict:
        try:
            orders = self.client.get_all_orders(symbol=symbol)
            return orders
        except exceptions.BinanceAPIException as e:
            print(f"Error getting orders. {e.message}")

    def _get_assets_balance(self) -> list:
        try:
            balances = self.client.get_account()['balances']
            return balances
        except exceptions.BinanceAPIException as e:
            print(f"Error. {e.message}")
        pass

    def _get_symbol_avg_price(self, symbol: str) -> float:
        try:
            symbol_avg_price = float(self.client.get_avg_price(symbol=symbol)['price'])
            return round_step_size(symbol_avg_price, self.symbols_data[symbol]['tick_size'])
        except exceptions.BinanceAPIException as e:
            print(e.message)

    def _get_symbol_order(self, symbol: str, orderId: str) -> dict:
        try:
            order = self.client.get_order(symbol=symbol, orderId=orderId)
            return order
        except exceptions.BinanceAPIException as e:
            print(e.message)

    def _get_ticksize(self, symbol) -> float:
        price_filter_index = 0
        try:
            symbol_filters = self.client.get_symbol_info(symbol=symbol)['filters']
            ticksize = float(symbol_filters[price_filter_index]['tickSize'])
            return ticksize
        except exceptions.BinanceAPIException as e:
            print(e.message)

    # GETTERS END

    # OTHER API CALLS START
    def _cancel_symbol_order(self, symbol: str, orderId: str) -> dict:
        try:
            result = self.client.cancel_order(symbol=symbol, orderId=orderId)
            return result
        except exceptions.BinanceAPIException as e:
            print(e.message)

    # makes order at given price and returns result if successful or not
    def _make_order(self, symbol: str, side: str, quantity: float, price: float = None) -> bool:
        order_completed = False
        if self.order_type == Client.ORDER_TYPE_LIMIT:
            price = self._get_symbol_avg_price(symbol)
        try:
            response = self.client.create_order(
                symbol=symbol,
                side=side,
                # TODO: decide maybe implement stop limit loss? this was ORDER_TYPE_LIMIT b4
                type=self.order_type,
                # TODO: make this parameter from func so it works with both types of orders?
                timeInForce=self.time_in_force,
                quantity=quantity,
                price=price,
                newOrderRespType=ORDER_RESP_TYPE_RESULT
                # TODO: make response part of config?
                # newOrderRespType=ORDER_RESP_TYPE_ACK
            )
            # TODO: make logging?
            print(f"{response['side']} {response['type']} {response['symbol']} {response['status']=}")
            # TODO: fix this block
            if self.time_in_force == Client.TIME_IN_FORCE_FOK:
                if response['status'] == Client.ORDER_STATUS_EXPIRED:
                    return False
            order_completed = True
        except exceptions.BinanceAPIException as e:
            print(f"Error executing order for {symbol}. Order type {side}. Price {price}. {e.message}")
        return order_completed

    # OTHER API CALLS END

    # MENU OPTIONS START
    def _save_pairs_data(self) -> None:
        validate(instance=self.pairs_data, schema=pairs_schema)
        with open("pairs.json", "w") as pairs_file:
            json.dump(self.pairs_data, pairs_file, indent=2, separators=(',', ': '))
        pass

    def _print_balances(self) -> None:
        balances = self._get_assets_balance()
        for balance in balances:
            print(balance)
        pass

    def _print_positions(self) -> None:
        for key, value in self.pairs_data.items():
            print(f"{key} position: {value['position']}")
        pass

    def _print_symbol_orders(self) -> None:
        symbol = input("Enter symbol: ")
        orders = self._get_symbol_orders(symbol=symbol)
        # TODO: if order are none this crashes
        orders = orders[-5:]
        for order in orders:
            print(f"id:{order['orderId']} price:{order['price']} side:{order['side']} executed:{order['executedQty']}")
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
    # MENU OPTIONS END


config_schema = {
    "type": "object",
    "required": ["api_key", "api_secret", "timeout", "long_term", "short_term", "interval", "order_type",
                 "time_in_force"],
    "properties": {
        "api_key": {"type": "string"},
        "api_secret": {"type": "string"},
        # how often to check for trades
        "timeout": {"type": "integer", "minimum": 60, "maximum": 3600},
        # from python-binance source code, these are enums used for kline intervals
        "interval": {"enum": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M"]},
        # how many data points to take from given interval
        "long_term": {"type": "integer", "minimum": 15},
        "short_term": {"type": "integer", "minimum": 5},
        # there are others like "STOP LOSS" and "TAKE_PROFIT_MARKET"
        "order_type": {"enum": ["MARKET", "LIMIT"]},
        # TODO: if order_type is MARKET, time_in_force should be None
        "time_in_force": {"enum": ["GTC", "IOC", "FOK", None]}
    },
    "additionalProperties": False
}

pairs_schema = {
    "type": "object",
    "minProperties": 1,
    "maxProperties": 5,
    "patternProperties": {
        "^[A-Z]+$": {
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
                }
            },
            "required": [
                "position",
                "trade_quantity"
            ]
        }
    },
    "additionalProperties": False
}
