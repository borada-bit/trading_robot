import json
import binance_util


class Robot:

    def __init__(self):
        with open('config.json', 'r') as config_file:
            data = json.load(config_file)
            self.timeout = data['timeout']
            self.long_term = data['long_term']
            self.short_term = data['short_term']
            self.client = binance_util.init_client(data['api_key'], data['api_secret'])

    pass
