import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

def timestamp_to_readable(timestamp) -> datetime:
    return datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')

def graph_orders(symbol, orders_df, prices_df) -> None:
    plt.plot(prices_df['Open Time'], prices_df['Close'])
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.legend()
    plt.xticks(rotation=90)

    for order in orders_df.itertuples():
        color = 'red'
        if float(order.executed) > 0:
            color = 'blue' if order.side == 'BUY' else 'green'
        plt.scatter(mdates.datestr2num(timestamp_to_readable(order.time)), order.price, marker='o', alpha=0.8, color=color, label='Trade')

    plt.savefig(f"{timestamp_to_readable(orders_df['time'].iloc[0])}_{symbol}_graph.png")
