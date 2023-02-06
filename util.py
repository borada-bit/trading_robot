import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

def timestamp_to_readable(timestamp) -> datetime:
    return datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')

def graph_orders(symbol, orders_df, prices_df) -> None:
    plt.figure(figsize=(10, 6))
    plt.plot(prices_df['Open Time'], prices_df['Close'])
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.xticks(rotation=90)

    unique_labels = set()
    for order in orders_df.itertuples():
        color = 'red'
        if order.executed > 0:
            color = 'blue' if order.side == 'BUY' else 'green'
        
        label = 'RETRY' if color == 'red' else order.side
        if label not in unique_labels:
            unique_labels.add(label)
        else:
            label = None

        plt.scatter(mdates.datestr2num(timestamp_to_readable(order.time)), order.price, marker='o', alpha=1.0, color=color, label=label)

    plt.legend()
    plt.savefig(f"{timestamp_to_readable(orders_df['time'].iloc[0])}_{symbol}_graph.png", bbox_inches='tight')
    plt.close()
