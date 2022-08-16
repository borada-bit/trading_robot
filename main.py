from binance import Client, exceptions
from binance.enums import *
import config


def main():
    client = Client(config.api_key, config.api_secret)
    try:
        client.ping()
    except exceptions.BinanceAPIException as e:
        print(f"Error connecting to client. Error code :{e.status_code}. Message: {e.message}")

    try:
        # https://dev.binance.vision/t/what-does-the-percent-price-filter-mean/134
        info = client.get_symbol_info('ADAEUR')
        info_price = client.get_symbol_ticker(symbol='ADAEUR')
        # print(info_price)
        # print(info['PERCENT_PRICE'])
        # print(info['filters'][1])
        val1 = info_price['price']
        val2 = info['filters'][1]['multiplierDown']
        print(f"{val1=} and {val2=}")
        # print(price)

        buy_loweset_price = float(val1) * float(val2)
        round(buy_loweset_price, 5)
        print(buy_loweset_price)

        order = client.create_test_order(
            symbol='ADAEUR',
            side=SIDE_BUY,
            type=ORDER_TYPE_LIMIT,
            timeInForce=TIME_IN_FORCE_GTC,
            quantity=100,
            price="0.5084")
            # price=str(buy_loweset_price))

        print(order)
    except exceptions.BinanceAPIException as e:
        print(f"Error placing test order. Message: {e.message}")

    # print(client.get_account())
    # print(client.get_asset_balance("ada"))
    # print(client.get_exchange_info())
    # cia yra visa info kaip vadinasi tradinami simboliai
    # print(client.get_orderbook_tickers())


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
