import pandas as pd

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  
        self.cost = 2          

    def run_strategy(self, start_date, session_type="全時段", sl_multi=1.5, tp_multi=3.0):
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

        # 確保價格為浮點數
        df_30m['close'] = df_30m['close'].astype(float)
        for col in ['open', 'high', 'low', 'close']:
            df_5m[col] = df_5m[col].astype(float)

        # 1. 計算 EMA20
        df_30m['EMA20'] = df_30m['close'].ewm(span=20, adjust=False).mean()

        # 2. 計算 RSI14
        diff = df_5m['close'].diff()
        up = diff.where(diff > 0, 0.0)
        down = -diff.where(diff < 0, 0.0)
        ema_up = up.ewm(alpha=1/14, adjust=False).mean()
        ema_down = down.ewm(alpha=1/14, adjust=False).mean()
        rs = ema_up / ema_down
        df_5m['RSI'] = 100 - (100 / (1 + rs))
        df_5m['RSI'] = df_5m['RSI'].fillna(50)

        # 🚀 3. 計算 ATR (14期真實波動幅度)
        tr1 = df_5m['high'] - df_5m['low']
        tr2 = (df_5m['high'] - df_5m['close'].shift(1)).abs()
        tr3 = (df_5m['low'] - df_5m['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df_5m['ATR'] = tr.rolling(window=14).mean().bfill() # 平滑計算並填補開頭空值

        trades = []
        position = 0  
        entry_price = 0
        target_sl = 0
        target_tp = 0

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
            current_atr = df_5m['ATR'].iloc[i] # 取得當下 K 線的 ATR

            if position == 1: # 多單持倉
                if low <= target_sl:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': target_sl, 'desc': '停損出場'})
                    position = 0
                elif high >= target_tp:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': target_tp, 'desc': '停利出場'})
                    position = 0
                elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': price, 'desc': '反轉平倉'})
                    position = 0

            elif position == -1: # 空單持倉
                if high >= target_sl:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': target_sl, 'desc': '停損出場'})
                    position = 0
                elif low <= target_tp:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': target_tp, 'desc': '停利出場'})
                    position = 0
                elif price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': price, 'desc': '反轉平倉'})
                    position = 0

            if position == 0: # 空手尋找進場
                if price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                    entry_price = price
                    # 動態計算停損停利點位
                    target_sl = entry_price - (current_atr * sl_multi)
                    target_tp = entry_price + (current_atr * tp_multi)
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': entry_price, 'desc': '多單進場'})
                    position = 1
                    
                elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                    entry_price = price
                    # 動態計算停損停利點位
                    target_sl = entry_price + (current_atr * sl_multi)
                    target_tp = entry_price - (current_atr * tp_multi)
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': entry_price, 'desc': '空單進場'})
                    position = -1

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
