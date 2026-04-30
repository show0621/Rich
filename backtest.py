import pandas as pd
import ta

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  # 微台每點 10 元
        self.cost = 2          # 單邊交易成本 2 點

    def run_strategy(self, start_date, session_type="全時段", sl_points=20, tp_points=40):
        # 1. 基礎時間與日夜盤過濾
        df = self.df_1m.loc[start_date:].copy()
        if session_type == "日盤 (08:45-13:45)":
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        # 2. 轉換時框
        df_30m = df.resample('30T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        df_5m = df.resample('5T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

        # 3. 計算指標
        df_30m['EMA20'] = ta.trend.ema_indicator(df_30m['close'], window=20)
        df_5m['RSI'] = ta.momentum.rsi(df_5m['close'], window=14)

        # 4. 狀態機回測核心 (含停損停利)
        trades = []
        position = 0  # 0: 空手, 1: 多單, -1: 空單
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

            # --- 檢查出場條件 (SL / TP / 動能反轉) ---
            if position == 1: # 多單持倉中
                if low <= entry_price - sl_points:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': entry_price - sl_points, 'desc': '停損出場'})
                    position = 0
                elif high >= entry_price + tp_points:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': entry_price + tp_points, 'desc': '停利出場'})
                    position = 0
                elif price < last_trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                    trades.append({'time': curr_time, 'type': 'SELL', 'price': price, 'desc': '反轉平倉'})
                    position = 0

            elif position == -1: # 空單持倉中
                if high >= entry_price + sl_points:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': entry_price + sl_points, 'desc': '停損出場'})
                    position = 0
                elif low <= entry_price - tp_points:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': entry_price - tp_points, 'desc': '停利出場'})
                    position = 0
                elif price > last_trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                    trades.append({'time': curr_time, 'type': 'BUY', 'price': price, 'desc': '反轉平倉'})
                    position = 0

            # --- 檢查進場條件 (必須是空手) ---
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
        # 確保交易是一對一對的 (剔除最後未平倉的單)
        if len(trades) % 2 != 0:
            trades = trades[:-1]
            
        if len(trades) < 2: return {"狀態": "訊號不足", "交易次數": 0}
        
        profits = []
        for i in range(0, len(trades), 2):
            entry, exit_trade = trades[i], trades[i+1]
            diff = (exit_trade['price'] - entry['price']) if entry['type'] == 'BUY' else (entry['price'] - exit_trade['price'])
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
            "期望值/筆": f"{p_series.mean():.1f} TWD"
        }
