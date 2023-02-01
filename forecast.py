from statsmodels.tsa.arima.model import ARIMA
from pmdarima import auto_arima

ARIMA_MAX_P_ORDER = 4
ARIMA_MAX_D_ORDER = 2
ARIMA_MAX_Q_ORDER = 4


def model_predict_arima(symbol: str, df):
    print(f'Starting forecasting for {symbol}')

    df.set_index('Open Time', inplace=True)
    df = list(df['Close'])

    order = best_params_arima(df)

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
