import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.arima.model import ARIMA
from pmdarima import auto_arima
from sklearn.metrics import mean_squared_error as mse

ARIMA_MAX_P_ORDER = 4
ARIMA_MAX_D_ORDER = 2
SEASONALITY_PERIOD = 4  # because 15min
ARIMA_MAX_Q_ORDER = 4

def binance_klines_to_df(klines):
    klines = np.array(klines)
    df = pd.DataFrame(klines.reshape(-1, 12), dtype=float, columns=('Open Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset vol', 'Num trades', 'Taker base vol', 'Taker quote vol', 'Ignore'))
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
    return df

def model_predict_arima(symbol: str, klines):
    dir_prefix = f'./results/{symbol}/'
    print(f'Starting forecasting for {symbol}')

    df = klines
    df.set_index('Open Time', inplace=True)
    df = list(df['Close'])

    order = best_params_arima(df)
    # print(f'Best order: {order=}')

    model = ARIMA(df, order=order)
    model_fit = model.fit()
    output = model_fit.forecast(steps=1)
    yhat = output[0]
    return yhat

def best_params_arima(df):
    # Define the range of values for each parameter
    arima_order = (ARIMA_MAX_P_ORDER, ARIMA_MAX_D_ORDER, ARIMA_MAX_Q_ORDER)

    # Create an ARIMA model
    arima_model = auto_arima(df, order=arima_order, seasonal=False, stepwise=True, suppress_warnings=True,
                             error_action='ignore')

    return arima_model.order
