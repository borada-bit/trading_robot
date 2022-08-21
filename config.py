api_key = "key"
api_secret = "secret"
# specifies how much time to spend idling/waiting for command in main bot loop
TIMEOUT = 60


def get_pairs() -> list:
    return ['BTCBUSD', 'LTCBUSD', 'XRPBUSD', 'BNBBTC', 'ETHBTC']
