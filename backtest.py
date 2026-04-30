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
            
        if session_type == "日盤 (08:45-13:45)":
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        # --- 基礎時框轉換 ---
        df_main = df.resample(timeframe).agg({
            'open':'first','high':'max','low':'min','close':'last', 'volume':'sum'
        }).dropna()
        for col in ['open', 'high', 'low', 'close']: df_main[col] = df_main[col].astype(float)
        
        # 準備基礎指標 (ATR 用於輔助風控)
        tr = pd.concat([df_main['high']-df_main['low'], (df_main['high']-df_main['close'].shift(1)).abs(), (df_main['low']-df_main['close'].shift(1)).abs()], axis=1).max(axis=1)
        df_main['ATR'] = tr.rolling(window=20).mean().bfill()

        # --- 🚀 趨勢線/型態識別邏輯 ---
        if strategy_type == "趨勢線突破":
            window = params.get('pivot_window', 5)
            df_main['pivot_h'] = np.nan
            df_main['pivot_l'] = np.nan
            
            # 尋找局部高低點 (Pivots)
            for i in range(window, len(df_main) - window):
                if df_main['high'].iloc[i] == df_main['high'].iloc[i-window:i+window+1].max():
                    df_main.iloc[i, df_main.columns.get_loc('pivot_h')] = df_main['high'].iloc[i]
                if df_main['low'].iloc[i] == df_main['low'].iloc[i-window:i+window+1].min():
                    df_main.iloc[i, df_main.columns.get_loc('pivot_l')] = df_main['low'].iloc[i]

        # RSI/布林指標 (保留原功能)
        elif strategy_type == "RSI波段":
            diff = df_main['close'].diff()
            up, down = diff.where(diff > 0, 0.0), -diff.where(diff < 0, 0.0)
            ema_up, ema_down = up.ewm(alpha=1/params['rsi_period'], adjust=False).mean(), down.ewm(alpha=1/params['rsi_period'], adjust=False).mean()
            df_main['RSI'] = 100 - (100 / (1 + ema_up / ema_down))

        # --- 回測核心邏輯 ---
        trades = []
        position = 0; entry_price = 0; target_sl = 0; highest_high = 0; lowest_low = 0
        
        # 趨勢線追蹤變數
        last_h_pivots = [] # 儲存最近兩個高點 (index, price)
        last_l_pivots = [] # 儲存最近兩個低點 (index, price)

        for i in range(10, len(df_main)):
            curr_time = df_main.index[i]
            row = df_main.iloc[i]
            
            # 更新 Pivots 隊列 (模擬即時重劃線)
            if not np.isnan(df_main['pivot_h'].iloc[i-window]):
                last_h_pivots.append((i-window, df_main['pivot_h'].iloc[i-window]))
                if len(last_h_pivots) > 2: last_h_pivots.pop(0)
            if not np.isnan(df_main['pivot_l'].iloc[i-window]):
                last_l_pivots.append((i-window, df_main['pivot_l'].iloc[i-window]))
                if len(last_l_pivots) > 2: last_l_pivots.pop(0)

            # 計算當前上線與下線的預測值
            upper_line = np.nan
            lower_line = np.nan
            if len(last_h_pivots) == 2:
                p1, p2 = last_h_pivots
                slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
                upper_line = p2[1] + slope * (i - p2[0])
            if len(last_l_pivots) == 2:
                p1, p2 = last_l_pivots
                slope = (p2[1] - p1[1]) / (p2[0] - p1[0])
                lower_line = p2[1] + slope * (i - p2[0])

            # 交易邏輯
            if position != 0:
                # 移動停損/停利 (通用)
                if position == 1:
                    highest_high = max(highest_high, row['high'])
                    target_sl = max(target_sl, highest_high - (row['ATR'] * sl_multi))
                    # 💡 趨勢線特有停損：如果跌破了「新畫出的」下線
                    if not np.isnan(lower_line) and row['close'] < lower_line:
                        trades.append({'time': curr_time, 'type': 'SELL', 'price': row['close'], 'desc': '趨勢線反轉停損', 'cost': cost_points})
                        position = 0
                    elif row['low'] <= target_sl:
                        trades.append({'time': curr_time, 'type': 'SELL', 'price': target_sl, 'desc': '波段移動停損', 'cost': cost_points})
                        position = 0
                else:
                    lowest_low = min(lowest_low, row['low'])
                    target_sl = min(target_sl, lowest_low + (row['ATR'] * sl_multi))
                    # 💡 趨勢線特有停損：如果突破了「新畫出的」上線
                    if not np.isnan(upper_line) and row['close'] > upper_line:
                        trades.append({'time': curr_time, 'type': 'BUY', 'price': row['close'], 'desc': '趨勢線反轉停損', 'cost': cost_points})
                        position = 0
                    elif row['high'] >= target_sl:
                        trades.append({'time': curr_time, 'type': 'BUY', 'price': target_sl, 'desc': '波段移動停損', 'cost': cost_points})
                        position = 0

            if position == 0:
                # 趨勢線突破進場
                if strategy_type == "趨勢線突破":
                    if not np.isnan(upper_line) and row['close'] > upper_line:
                        entry_signal = 1
                    elif not np.isnan(lower_line) and row['close'] < lower_line:
                        entry_signal = -1
                    else: entry_signal = 0
                
                # 其他策略 (RSI等)
                else:
                    entry_signal = 0 # 之前的邏輯...

                if entry_signal != 0:
                    position = entry_signal; entry_price = row['close']
                    highest_high = row['high']; lowest_low = row['low']
                    target_sl = entry_price - (row['ATR'] * sl_multi) if position == 1 else entry_price + (row['ATR'] * sl_multi)
                    trades.append({'time': curr_time, 'type': 'BUY' if position == 1 else 'SELL', 'price': row['close'], 'desc': '趨勢線突破進場', 'cost': cost_points})

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
