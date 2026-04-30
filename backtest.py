import pandas as pd
import numpy as np

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  

    def run_strategy(self, strategy_type, start_date, session_type="全時段", 
                     sl_multi=2.0, tp_multi=8.0, params=None, 
                     cost_points=3.5, timeframe='30min'):
        
        try:
            df = self.df_1m.loc[start_date:].copy()
        except KeyError:
            df = self.df_1m.copy()
            
        # 波段交易建議使用全時段，包含夜盤
        if session_type == "日盤 (08:45-13:45)":
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        # --- 長線趨勢濾網 (維持 60分 EMA200) ---
        df_trend_base = df.resample('60min').agg({'close':'last'}).dropna()
        df_trend_base['EMA200'] = df_trend_base['close'].ewm(span=200, adjust=False).mean()
        df_trend = df_trend_base[['EMA200']].reindex(df.index, method='ffill')

        # --- 主交易時框 (30分 或 60分) ---
        df_main = df.resample(timeframe).agg({
            'open':'first','high':'max','low':'min','close':'last', 'volume':'sum'
        }).dropna()
        for col in ['open', 'high', 'low', 'close']: df_main[col] = df_main[col].astype(float)
        
        # 合併濾網
        df_main = df_main.join(df_trend)

        # 指標計算
        # ATR 週期拉長至 20 確保波段穩定
        tr = pd.concat([df_main['high']-df_main['low'], (df_main['high']-df_main['close'].shift(1)).abs(), (df_main['low']-df_main['close'].shift(1)).abs()], axis=1).max(axis=1)
        df_main['ATR'] = tr.rolling(window=20).mean().bfill()

        if strategy_type == "RSI波段":
            diff = df_main['close'].diff()
            up, down = diff.where(diff > 0, 0.0), -diff.where(diff < 0, 0.0)
            ema_up = up.ewm(alpha=1/params['rsi_period'], adjust=False).mean()
            ema_down = down.ewm(alpha=1/params['rsi_period'], adjust=False).mean()
            df_main['RSI'] = 100 - (100 / (1 + ema_up / ema_down))
        elif strategy_type == "布林波段":
            df_main['MA'] = df_main['close'].rolling(window=params['bb_period']).mean()
            df_main['std'] = df_main['close'].rolling(window=params['bb_period']).std()
            df_main['UB'] = df_main['MA'] + params['bb_std'] * df_main['std']
            df_main['LB'] = df_main['MA'] - params['bb_std'] * df_main['std']

        # --- 回測核心邏輯 (跨日波段) ---
        trades = []
        position = 0; entry_price = 0; target_sl = 0; highest_high = 0; lowest_low = 0

        for i in range(2, len(df_main)):
            curr_time = df_main.index[i]
            row = df_main.iloc[i]; prev = df_main.iloc[i-1]
            price = row['close']

            if position != 0:
                # 移動停損 (波段版：停損倍數放寬)
                if position == 1:
                    highest_high = max(highest_high, row['high'])
                    target_sl = max(target_sl, highest_high - (row['ATR'] * sl_multi))
                    if row['low'] <= target_sl:
                        trades.append({'time': curr_time, 'type': 'SELL', 'price': target_sl, 'desc': '波段出場', 'cost': cost_points})
                        position = 0
                else:
                    lowest_low = min(lowest_low, row['low'])
                    target_sl = min(target_sl, lowest_low + (row['ATR'] * sl_multi))
                    if row['high'] >= target_sl:
                        trades.append({'time': curr_time, 'type': 'BUY', 'price': target_sl, 'desc': '波段出場', 'cost': cost_points})
                        position = 0
                
                # 達標大停利 (TP 設大，讓利潤奔跑)
                if position != 0 and abs(price - entry_price) >= row['ATR'] * tp_multi:
                    trades.append({'time': curr_time, 'type': 'SELL' if position == 1 else 'BUY', 'price': price, 'desc': '獲利落袋', 'cost': cost_points})
                    position = 0

            if position == 0:
                is_long_trend = price > row['EMA200']
                is_short_trend = price < row['EMA200']

                entry_signal = 0
                if strategy_type == "RSI波段":
                    if row['RSI'] < params['rsi_lower'] and prev['RSI'] >= params['rsi_lower'] and is_long_trend: entry_signal = 1
                    elif row['RSI'] > params['rsi_upper'] and prev['RSI'] <= params['rsi_upper'] and is_short_trend: entry_signal = -1
                elif strategy_type == "布林波段":
                    if price < row['LB'] and is_long_trend: entry_signal = 1
                    elif price > row['UB'] and is_short_trend: entry_signal = -1

                if entry_signal != 0:
                    position = entry_signal; entry_price = price
                    highest_high = row['high']; lowest_low = row['low']
                    target_sl = entry_price - (row['ATR'] * sl_multi) if position == 1 else entry_price + (row['ATR'] * sl_multi)
                    trades.append({'time': curr_time, 'type': 'BUY' if position == 1 else 'SELL', 'price': price, 'desc': '波段進場', 'cost': cost_points})

        return self.calculate_metrics(trades, cost_points), trades

    def calculate_metrics(self, trades, cost_per_side):
        if len(trades) % 2 != 0: trades = trades[:-1]
        if not trades: return {"狀態": "無交易", "交易次數": 0}
        profits = []
        for i in range(0, len(trades), 2):
            en, ex = trades[i], trades[i+1]
            diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
            profits.append((diff - (cost_per_side * 2)) * self.point_value)
        p = pd.Series(profits)
        return {"勝率": f"{len(p[p>0])/len(p):.1%}", "淨獲利": f"{p.sum():,.0f} TWD", "交易次數": len(p), "平均獲利/筆": f"{p.mean():.1f} TWD"}
