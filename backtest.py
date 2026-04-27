import pandas as pd
import pandas_ta as ta

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.cost = 2  # 單邊交易成本點數 (手續費+稅)
        self.point_value = 10  # 微台每點 10 元

    def run_strategy(self, start_time, end_time):
        df = self.df_1m.loc[start_time:end_time].copy()
        
        # 轉換時框
        df_30m = df.resample('30T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()
        df_5m = df.resample('5T').agg({'open':'first','high':'max','low':'min','close':'last'}).dropna()

        # 指標計算
        df_30m['EMA20'] = ta.ema(df_30m['close'], length=20)
        df_5m['RSI'] = ta.rsi(df_5m['close'], length=14)

        # 訊號邏輯 (長線看 EMA20, 短線看 RSI)
        trades = []
        for i in range(1, len(df_5m)):
            # 獲取對應的 30分趨勢
            current_time = df_5m.index[i]
            trend_30m = df_30m.loc[:current_time].iloc[-1]
            
            # 多頭：30分在 EMA20 之上 + 5分 RSI 突破 50
            if df_5m['close'].iloc[i] > trend_30m['EMA20'] and df_5m['RSI'].iloc[i] > 50 and df_5m['RSI'].iloc[i-1] <= 50:
                trades.append({'time': current_time, 'type': 'BUY', 'price': df_5m['close'].iloc[i]})
            
            # 空頭：30分在 EMA20 之下 + 5分 RSI 跌破 50
            elif df_5m['close'].iloc[i] < trend_30m['EMA20'] and df_5m['RSI'].iloc[i] < 50 and df_5m['RSI'].iloc[i-1] >= 50:
                trades.append({'time': current_time, 'type': 'SELL', 'price': df_5m['close'].iloc[i]})

        return self.calculate_performance(trades)

    def calculate_performance(self, trades):
        if len(trades) < 2: return {"msg": "交易次數不足"}
        
        pnl = []
        for i in range(0, len(trades)-1, 2): # 簡化：一買一賣為一組
            entry = trades[i]
            exit = trades[i+1]
            diff = (exit['price'] - entry['price']) if entry['type'] == 'BUY' else (entry['price'] - exit['price'])
            net_pnl = (diff - (self.cost * 2)) * self.point_value
            pnl.append(net_pnl)
            
        win_rate = len([p for p in pnl if p > 0]) / len(pnl) if pnl else 0
        total_pnl = sum(pnl)
        expectancy = total_pnl / len(pnl) if pnl else 0
        
        # 最大回撤 (MDD) 簡化版
        cum_pnl = pd.Series(pnl).cumsum()
        mdd = (cum_pnl.cummax() - cum_pnl).max()
        
        return {"勝率": f"{win_rate:.2%}", "期望值": f"{expectancy:.1f} TWD", "最大回撤": f"{mdd:.1f} TWD", "總交易次數": len(pnl)}
