import pandas as pd
import ta
import datetime

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10
        self.cost = 2

    def run_strategy(self, start_date, session_type="全時段"):
        # 1. 基礎時間過濾
        df = self.df_1m.loc[start_date:].copy()
        
        # 2. 加入日夜盤過濾邏輯
        if session_type == "日盤 (08:45-13:45)":
            # 僅保留日盤時段
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            # 僅保留夜盤時段 (跨日處理)
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "該時段無資料", "交易次數": 0}

        # 3. 轉換時框 (注意：日夜盤切換處會產生跳空，resample 會自動處理)
        df_30m = df.resample('30T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        df_5m = df.resample('5T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

        # 4. 計算指標與回測邏輯 (保持原樣)
        df_30m['EMA20'] = ta.trend.ema_indicator(df_30m['close'], window=20)
        df_5m['RSI'] = ta.momentum.rsi(df_5m['close'], window=14)

        trades = []
        for i in range(1, len(df_5m)):
            curr_time = df_5m.index[i]
            trend_data = df_30m.loc[:curr_time]
            if trend_data.empty: continue
            
            last_trend = trend_data.iloc[-1]
            price = df_5m['close'].iloc[i]
            rsi = df_5m['RSI'].iloc[i]
            prev_rsi = df_5m['RSI'].iloc[i-1]

            if price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                trades.append({'time': curr_time, 'type': 'BUY', 'price': price})
            elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                trades.append({'time': curr_time, 'type': 'SELL', 'price': price})

        return self.calculate_metrics(trades)

    # calculate_metrics 保持不變
