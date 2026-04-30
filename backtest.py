import pandas as pd
import ta

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  # 微台每點 10 元
        self.cost = 2          # 單邊交易成本 2 點

    def run_strategy(self, start_date):
        # 切割時間範圍
        df = self.df_1m.loc[start_date:].copy()
        
        # 轉換時框 (5m, 15m, 30m)
        df_30m = df.resample('30T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        df_15m = df.resample('15T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        df_5m = df.resample('5T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

        # 計算指標
        df_30m['EMA20'] = ta.trend.ema_indicator(df_30m['close'], window=20)
        df_5m['RSI'] = ta.momentum.rsi(df_5m['close'], window=14)

        trades = []
        # 多時框邏輯演算法
        for i in range(1, len(df_5m)):
            curr_time = df_5m.index[i]
            # 取得對應時間的 30分趨勢
            trend_30 = df_30m.loc[:curr_time]
            if trend_30.empty: continue
            
            last_trend = trend_30.iloc[-1]
            price = df_5m['close'].iloc[i]
            rsi = df_5m['RSI'].iloc[i]
            prev_rsi = df_5m['RSI'].iloc[i-1]

            # 多頭進場：30分在 EMA20 之上 + 5分 RSI 突破 50
            if price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                trades.append({'time': curr_time, 'type': 'BUY', 'price': price})
            # 空頭進場：30分在 EMA20 之下 + 5分 RSI 跌破 50
            elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                trades.append({'time': curr_time, 'type': 'SELL', 'price': price})

        return self.calculate_metrics(trades)

    def calculate_metrics(self, trades):
        if len(trades) < 2: return {"狀態": "訊號不足", "交易次數": 0}
        
        profits = []
        for i in range(0, len(trades)-1, 2):
            b, s = trades[i], trades[i+1]
            diff = (s['price'] - b['price']) if b['type'] == 'BUY' else (b['price'] - s['price'])
            net = (diff - (self.cost * 2)) * self.point_value
            profits.append(net)

        p_series = pd.Series(profits)
        cum_pnl = p_series.cumsum()
        win_rate = len(p_series[p_series > 0]) / len(p_series) if not p_series.empty else 0
        mdd = (cum_pnl.cummax() - cum_pnl).max() if not cum_pnl.empty else 0

        return {
            "勝率": f"{win_rate:.1%}",
            "累積損益": f"{p_series.sum():,.0f} TWD",
            "最大回撤 (MDD)": f"{mdd:,.0f} TWD",
            "總交易次數": len(profits),
            "期望值": f"{p_series.mean():.1f} TWD"
        }
