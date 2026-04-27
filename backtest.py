import pandas as pd
import ta

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  # 微台每點 10 元
        self.fee = 2           # 單邊滑價+稅 2 點

    def prepare_data(self, df, tf):
        """轉換時框並計算指標"""
        df_tf = df.resample(tf).agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        # 使用 ta 函式庫計算
        df_tf['EMA20'] = ta.trend.ema_indicator(df_tf['close'], window=20)
        df_tf['RSI'] = ta.momentum.rsi(df_tf['close'], window=14)
        return df_tf

    def run_strategy(self, start_date):
        df_range = self.df_1m.loc[start_date:].copy()
        df_30m = self.prepare_data(df_range, '30T')
        df_5m = self.prepare_data(df_range, '5T')

        trades = []
        # 簡單策略：30分定趨勢，5分找 RSI 交叉
        for i in range(1, len(df_5m)):
            curr_time = df_5m.index[i]
            # 找到對應的 30分 K 趨勢
            trend_data = df_30m.loc[:curr_time]
            if trend_data.empty: continue
            
            trend = trend_data.iloc[-1]
            price = df_5m['close'].iloc[i]
            rsi = df_5m['RSI'].iloc[i]
            prev_rsi = df_5m['RSI'].iloc[i-1]

            # 多頭進場條件
            if price > trend['EMA20'] and rsi > 50 and prev_rsi <= 50:
                trades.append({'time': curr_time, 'type': 'BUY', 'price': price})
            # 空頭進場條件
            elif price < trend['EMA20'] and rsi < 50 and prev_rsi >= 50:
                trades.append({'time': curr_time, 'type': 'SELL', 'price': price})

        return self.calculate_metrics(trades)

    def calculate_metrics(self, trades):
        if len(trades) < 2: return {"狀態": "資料不足或無訊號", "總交易數": 0}
        
        results = []
        for i in range(0, len(trades)-1, 2):
            entry, exit = trades[i], trades[i+1]
            diff = (exit['price'] - entry['price']) if entry['type'] == 'BUY' else (entry['price'] - exit['price'])
            net_profit = (diff - (self.fee * 2)) * self.point_value
            results.append(net_profit)

        win_rate = len([r for r in results if r > 0]) / len(results) if results else 0
        cum_pnl = pd.Series(results).cumsum()
        mdd = (cum_pnl.cummax() - cum_pnl).max() if not cum_pnl.empty else 0

        return {
            "勝率": f"{win_rate:.1%}",
            "累積損益": f"{sum(results):,.0f} TWD",
            "最大回撤 (MDD)": f"{mdd:,.0f} TWD",
            "總交易次數": len(results),
            "期望值/筆": f"{sum(results)/len(results):.1f} TWD" if results else 0
        }
