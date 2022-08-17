from typing import Optional

from binance import Client, exceptions
from binance.enums import *
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

def main():
    client = init_client()



# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
