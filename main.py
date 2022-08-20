from typing import Optional

from binance import Client, exceptions
from binance.enums import *
from inputimeout import inputimeout, TimeoutOccurred

import config


def init_client() -> Optional[Client]:
    client = Client(config.api_key, config.api_secret, testnet=True)
    try:
        client.ping()
        return client
    except exceptions.BinanceAPIException as e:
        print(f"Error connecting to client. Error code :{e.status_code}. Message: {e.message} Code: {e.code}")
        return None


def make_order_at_price(client: Client, symbol: str, quantity: float, price: float) -> bool:
    order_completed = False
    try:
        response = client.create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=quantity,
            price=price,
            newOrderRespType=ORDER_RESP_TYPE_ACK
        )
        print(f"{response=}")
        order_completed = True
    except exceptions.BinanceAPIException as e:
        print(f"Error executing order {e.message}")

    return order_completed


# prints orders for symbol
def print_symbol_orders(client: Client, symbol: str) -> None:
    orders = client.get_all_orders(symbol=symbol)
    print(f"Orders for {symbol}")
    for order in orders:
        print(f"{order['clientOrderId']=} {order['price']=} {order['executedQty']=} {order['cummulativeQuoteQty']=}")

    pass


# Prints each asset balance
def print_balances(client: Client) -> None:
    balances = client.get_account()['balances']

    for balance in balances:
        print(f"{balance}")

    pass


def print_menu():
    print("""
    1. Print balances.
    2. Print orders for symbol.
    ----------------------------------
    9. Print menu.
    0. Quit.""")


def main():
    client = init_client()

    print_menu()
    quit_loop = False
    while not quit_loop:
        try:
            user_string = inputimeout(prompt='>>', timeout=config.TIMEOUT)
        except TimeoutOccurred:
            user_string = "1"

        choice = -1
        try:
            choice = int(user_string)
        except TypeError and ValueError:
            print("Entered option is invalid!")

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
