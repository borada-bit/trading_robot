from typing import Optional, List

from binance import Client, exceptions
from binance.enums import *
from inputimeout import inputimeout, TimeoutOccurred

import config


def init_client(api_key: str, api_secret: str) -> Optional[Client]:
    client = Client(api_key, api_secret, testnet=True)
    try:
        client.ping()
        return client
    except exceptions.BinanceAPIException as e:
        print(f"Error connecting to client. Error code :{e.status_code}. Message: {e.message} Code: {e.code}")
        return None


# makes order at given price and returns result if successful or not
def make_limit_order(client: Client, symbol: str, side: str, quantity: float, price: float) -> bool:
    order_completed = False
    try:
        response = client.create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=quantity,
            price=price,
            newOrderRespType=ORDER_RESP_TYPE_ACK
        )
        print(f"Order {side} {symbol} for {price}. {response=}")
        order_completed = True
    except exceptions.BinanceAPIException as e:
        print(f"Error executing order for {symbol}. Order type {side}. Price {price}. {e.message}")

    return order_completed


# prints orders for symbol
def print_symbol_orders(client: Client, symbol: str) -> None:
    try:
    orders = client.get_all_orders(symbol=symbol)
    print(f"Orders for {symbol}")
    for order in orders:
            print(f"{order['orderId']=} {order['price']=} {order['side']=} {order['cummulativeQuoteQty']=}")
    except exceptions.BinanceAPIException as e:
        print(f"Error getting orders. {e.message}")

    pass


# prints each asset balance
def print_balances(client: Client) -> None:
    try:
    balances = client.get_account()['balances']
    for balance in balances:
        print(f"{balance}")
    except exceptions.BinanceAPIException as e:
        print(f"Error. {e.message}")

    pass


def print_menu():
    print("""
    1. Print balances.
    2. Print orders for symbol.
    ----------------------------------
    9. Print menu.
    0. Quit.""")


def get_pairs_historic_prices(client: Client, pairs: list, interval: str, limit: int, price_list: List[list]) -> bool:
    close_price_index = 4
    success = True
    try:
        for i, symbol in enumerate(pairs):
            klines = client.get_historical_klines(symbol, interval, limit=limit)
            if price_list[i]:
                price_list[i].pop()
            for kline in klines:
                price_list[i].insert(0, float(kline[close_price_index]))
    except exceptions.BinanceAPIException as e:
        success = False
        print(e.message)
    return success


# returns symbol avg price rounded by ndigits, on error returns -1.0
def get_symbol_avg_price(client: Client, symbol: str, ndigits: int) -> float:
    avg_price = -1.0
    try:
        avg_price = float(client.get_avg_price(symbol=symbol)['price'])
        avg_price = round(avg_price, ndigits)
    except exceptions.BinanceAPIException as e:
        print(e.message)
        
    return avg_price


def main():
    client = init_client(config.api_key, config.api_secret)

    print_menu()
    quit_loop = False
    while not quit_loop:
        try:
            user_string = inputimeout(prompt='>> ', timeout=config.TIMEOUT)
            choice = int(user_string)
        except TimeoutOccurred:
            choice = -9
        except ValueError:
            print("Entered option is invalid!")
            continue

        if choice == 0:
            print("Quiting!")
            quit_loop = True
        elif choice == 1:
            print_balances(client)
        elif choice == 2:
            symbol = input("Enter symbol: ")
            print_symbol_orders(client, symbol=symbol)
        elif choice == 9:
            print_menu()
        else:
            pass



if __name__ == '__main__':
    main()
