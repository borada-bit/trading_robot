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
DATA_SPLIT_PERCENTAGE = 0.9

def binance_klines_to_df(klines):
    klines = np.array(klines)
    df = pd.DataFrame(klines.reshape(-1, 12), dtype=float, columns=('Open Time','Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset volume', 'Number of trades', 'Taker  buy base asset volume', 'Taker buy quote asset volume', 'Ignore'))
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
    return df

def model_predict_arima(symbol: str, klines, seasonal = False):
    dir_prefix = f'./results/{symbol}/'
    print(f'Starting forecasting for {symbol}')

    df = binance_klines_to_df(klines)
    df = df[['Open Time', 'Close']]
    df.set_index('Open Time', inplace=True)
    print(df)

    print(f'Dataset total length: {len(df)}')

    to_row = int(len(df) * DATA_SPLIT_PERCENTAGE)
    training_data = list(df[0:to_row]['Close'])

    if seasonal:
        order, seasonal_order = best_params_arima_seasonal(training_data)
        print(f'best order: {order} {seasonal_order=}')
    else:
        order = best_params_arima(training_data)
        seasonal_order = None
        print(f'Best order: {order=}')

    testing_data = list(df[to_row:]['Close'])
    model_predictions = []
    for i in range(len(testing_data)):
        model = ARIMA(training_data, order=order, seasonal_order=seasonal_order)
        model_fit = model.fit()
        output = model_fit.forecast(steps=1)
        yhat = output[0]
        model_predictions.append(yhat)
        actual_test_value = testing_data[i]
        training_data.append(actual_test_value)

    plt.figure(figsize=(15, 9))
    plt.grid(True)
    # set date_range index to plot
    date_range = df[to_row:].index

    plt.plot(date_range, model_predictions, color='green', marker='x', linestyle='dashed',
             label=f'{symbol} predicted Price')
    plt.plot(date_range, testing_data, color='red', marker='o', label=f'{symbol} Actual Price')

    title = f'{symbol} Price prediction using {"S" if seasonal else ""}ARIMA{order}{seasonal_order if seasonal else ""}'
    plt.title(title)
    plt.xlabel('Dates')
    plt.ylabel('Price')

    print(f'{symbol=} results')
    print(f'mse: {mse(model_predictions, testing_data)}')
    mape = np.mean(np.abs(np.array(model_predictions) - np.array(testing_data)) / np.abs(testing_data))
    print(f'mape: {mape}')
    plt.legend()
    # plt.show()
    fig_name = f'{dir_prefix}{symbol}_{"seasonal" if seasonal else ""}_ARIMA{order}{seasonal_order if seasonal else ""}'
    plt.savefig(fig_name)
    plt.close('all')


def best_params_arima(df):
    # Define the range of values for each parameter
    arima_order = (ARIMA_MAX_P_ORDER, ARIMA_MAX_D_ORDER, ARIMA_MAX_Q_ORDER)

    # Create an ARIMA model
    arima_model = auto_arima(df, order=arima_order, seasonal=False, stepwise=True, suppress_warnings=True,
                             error_action='ignore')

    return arima_model.order


def best_params_arima_seasonal(df):
    arima_order = (ARIMA_MAX_P_ORDER, ARIMA_MAX_D_ORDER, ARIMA_MAX_Q_ORDER)
    seasonal_pdq = (ARIMA_MAX_P_ORDER, ARIMA_MAX_D_ORDER, ARIMA_MAX_Q_ORDER, SEASONALITY_PERIOD)
    model = auto_arima(df, start_p=1, start_q=1,
                       max_p=3, max_q=3, m=SEASONALITY_PERIOD,
                       start_P=0, seasonal=True,
                       d=1, D=1, trace=True,
                       error_action='ignore',
                       suppress_warnings=True,
                       stepwise=True)

    # Print the best parameters
    print("Best Parameters: ", model.order, model.seasonal_order)
    return model.order, model.seasonal_order
