import pandas as pd
import ta

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  
        self.cost = 2          

    def run_strategy(self, start_date, session_type="全時段", sl_points=20, tp_points=40):
        try:
            df = self.df_1m.loc[start_date:].copy()
        except KeyError:
            df = self.df_1m.copy()
            
        if session_type == "日盤 (08:45-13:45)":
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        df_30m = df.resample('30min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        df_5m = df.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

        # 防彈機制 1: 確保價格為浮點數，防止 SQLite 讀成字串
        df_30m['close'] = df_30m['close'].astype(float)
        df_5m['close'] = df_5m['close'].astype(float)

        # 防彈機制 2: 相容 ta 套件的新舊版本參數 (window vs n)
        try:
            df_30m['EMA20'] = ta.trend.ema_indicator(df_30m['close'], window=20)
            df_5m['RSI'] = ta.momentum.rsi(df_5m['close'], window=14)
        except TypeError:
            df_30m['EMA20'] = ta.trend.ema_indicator(df_30m['close'], n=20)
            df_5m['RSI'] = ta.momentum.rsi(df_5m['close'], n=14)

        trades = []
        position = 0  
        entry_price = 0

        for i in range(1, len(df_5m)):
            curr_time = df_5m.index[i]
            trend_data = df_30m.loc[:curr_time]
            if trend_data.empty: continue
            
            last_trend = trend_data.iloc[-1]
            price = df_5m['close'].iloc[i]
            high = df_5m['high'].iloc[i]
            low = df_5m['low'].iloc[i]
            rsi = df_5m['RSI'].iloc[i]
            prev_rsi = df_5m['RSI'].iloc[i-1]

            if position == 1:
                if low <= entry_price - sl_points:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': entry_price - sl_points, 'desc': '停損出場'})
                    position = 0
                elif high >= entry_price + tp_points:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': entry_price + tp_points, 'desc': '停利出場'})
                    position = 0
                elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': price, 'desc': '反轉平倉'})
                    position = 0

            elif position == -1:
                if high >= entry_price + sl_points:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': entry_price + sl_points, 'desc': '停損出場'})
                    position = 0
                elif low <= entry_price - tp_points:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': entry_price - tp_points, 'desc': '停利出場'})
                    position = 0
                elif price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': price, 'desc': '反轉平倉'})
                    position = 0

            if position == 0:
                if price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': price, 'desc': '多單進場'})
                    position = 1
                    entry_price = price
                elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': price, 'desc': '空單進場'})
                    position = -1
                    entry_price = price

        return self.calculate_metrics(trades), trades

    def calculate_metrics(self, trades):
        if len(trades) % 2 != 0: trades = trades[:-1]
        if len(trades) < 2: return {"狀態": "訊號不足", "交易次數": 0}
        
        profits = []
        for i in range(0, len(trades), 2):
            en, ex = trades[i], trades[i+1]
            diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
            profits.append((diff - (self.cost * 2)) * self.point_value)

        p_series = pd.Series(profits)
        cum_pnl = p_series.cumsum()
        return {
            "勝率": f"{len(p_series[p_series > 0]) / len(p_series):.1%}",
            "累積損益": f"{p_series.sum():,.0f} TWD",
            "最大回撤": f"{(cum_pnl.cummax() - cum_pnl).max():,.0f} TWD",
            "交易次數": len(profits),
            "期望值/筆": f"{p_series.mean():.1f} TWD"
        }
