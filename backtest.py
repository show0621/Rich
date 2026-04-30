import pandas as pd
import numpy as np

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.copy()
        if 'datetime' in self.df_1m.columns:
            self.df_1m['datetime'] = pd.to_datetime(self.df_1m['datetime'])
            self.df_1m = self.df_1m.set_index('datetime')
        self.point_value = 10  

    def run_strategy(self, strategy_type, start_date, session_type="全時段", 
                     sl_multi=2.0, tp_multi=8.0, params=None, 
                     cost_points=3.5, timeframe='30min', 
                     use_trend_filter=True):
        
        try:
            df = self.df_1m.loc[start_date:].copy()
        except:
            df = self.df_1m.copy()
            
        # --- 0. 精確時段選擇 ---
        if "日盤" in session_type:
            df = df.between_time('08:45', '13:45')
        elif "夜盤" in session_type:
            # 跨日處理：15:00 到 隔天 05:00
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        # --- 1. 時框轉換與欄位預建 ---
        df_main = df.resample(timeframe).agg({
            'open':'first','high':'max','low':'min','close':'last', 'volume':'sum'
        }).dropna()
        for col in ['open', 'high', 'low', 'close']: df_main[col] = df_main[col].astype(float)
        
        df_main['pivot_h'] = np.nan
        df_main['pivot_l'] = np.nan
        df_main['VOL_MA'] = df_main['volume'].rolling(window=20).mean()
        df_main['ATR'] = (df_main['high'] - df_main['low']).rolling(window=20).mean().bfill()
        
        # 長線趨勢濾網
        df_60m = df.resample('60min').agg({'close':'last'}).dropna()
        df_60m['EMA200'] = df_60m['close'].ewm(span=200, adjust=False).mean()
        df_main = df_main.join(df_60m[['EMA200']].reindex(df_main.index, method='ffill'))

        # --- 2. 各策略技術指標計算 ---
        if strategy_type == "趨勢線突破":
            window = params.get('pivot_window', 5)
            for i in range(window, len(df_main) - window):
                if df_main['high'].iloc[i] == df_main['high'].iloc[i-window:i+window+1].max():
                    df_main.iloc[i, df_main.columns.get_loc('pivot_h')] = df_main['high'].iloc[i]
                if df_main['low'].iloc[i] == df_main['low'].iloc[i-window:i+window+1].min():
                    df_main.iloc[i, df_main.columns.get_loc('pivot_l')] = df_main['low'].iloc[i]

        elif strategy_type == "RSI波段":
            diff = df_main['close'].diff()
            up, down = diff.where(diff > 0, 0.0), -diff.where(diff < 0, 0.0)
            alpha = 1/params.get('rsi_period', 14)
            ema_up = up.ewm(alpha=alpha, adjust=False).mean()
            ema_down = down.ewm(alpha=alpha, adjust=False).mean()
            df_main['RSI'] = 100 - (100 / (1 + ema_up / ema_down))

        elif strategy_type == "KD波段":
            low_min = df_main['low'].rolling(window=params.get('kd_period', 9)).min()
            high_max = df_main['high'].rolling(window=params.get('kd_period', 9)).max()
            rsv = (df_main['close'] - low_min) / (high_max - low_min) * 100
            df_main['K'] = rsv.ewm(com=2, adjust=False).mean()
            df_main['D'] = df_main['K'].ewm(com=2, adjust=False).mean()

        elif strategy_type == "MACD波段":
            fast = df_main['close'].ewm(span=params.get('macd_fast', 12), adjust=False).mean()
            slow = df_main['close'].ewm(span=params.get('macd_slow', 26), adjust=False).mean()
            df_main['DIF'] = fast - slow
            df_main['DEA'] = df_main['DIF'].ewm(span=params.get('macd_sig', 9), adjust=False).mean()

        # --- 3. 核心回測迴圈 ---
        trades = []
        position = 0; entry_price = 0; target_sl = 0; highest_high = 0; lowest_low = 0
        last_h_pivots = []; last_l_pivots = []
        window = params.get('pivot_window', 5)

        for i in range(20, len(df_main)):
            curr_time = df_main.index[i]; row = df_main.iloc[i]; prev = df_main.iloc[i-1]
            
            # 趨勢線重劃邏輯
            if not np.isnan(df_main['pivot_h'].iloc[i-window]):
                last_h_pivots.append((i-window, df_main['pivot_h'].iloc[i-window]))
                if len(last_h_pivots) > 2: last_h_pivots.pop(0)
            if not np.isnan(df_main['pivot_l'].iloc[i-window]):
                last_l_pivots.append((i-window, df_main['pivot_l'].iloc[i-window]))
                if len(last_l_pivots) > 2: last_l_pivots.pop(0)

            upper_line = np.nan; lower_line = np.nan
            if len(last_h_pivots) == 2:
                p1, p2 = last_h_pivots
                upper_line = p2[1] + ((p2[1]-p1[1])/(p2[0]-p1[0])) * (i - p2[0])
            if len(last_l_pivots) == 2:
                p1, p2 = last_l_pivots
                lower_line = p2[1] + ((p2[1]-p1[1])/(p2[0]-p1[0])) * (i - p2[0])

            # 出場邏輯
            if position != 0:
                is_exit = False
                if position == 1:
                    highest_high = max(highest_high, row['high'])
                    target_sl = max(target_sl, highest_high - (row['ATR'] * sl_multi))
                    if (not np.isnan(lower_line) and row['close'] < lower_line) or (row['low'] <= target_sl):
                        is_exit = True
                else:
                    lowest_low = min(lowest_low, row['low'])
                    target_sl = min(target_sl, lowest_low + (row['ATR'] * sl_multi))
                    if (not np.isnan(upper_line) and row['close'] > upper_line) or (row['high'] >= target_sl):
                        is_exit = True
                
                if is_exit:
                    trades.append({'time': curr_time, 'type': 'EXIT', 'price': row['close'], 'desc': '策略反轉/停損', 'cost': cost_points})
                    position = 0

            # 進場邏輯
            if position == 0:
                is_long_trend = row['close'] > row['EMA200'] if use_trend_filter else True
                is_short_trend = row['close'] < row['EMA200'] if use_trend_filter else True
                vol_ok = row['volume'] > (row['VOL_MA'] * params.get('volume_multi', 1.0))
                
                entry_signal = 0
                if strategy_type == "趨勢線突破" and vol_ok:
                    if not np.isnan(upper_line) and row['close'] > upper_line and is_long_trend: entry_signal = 1
                    elif not np.isnan(lower_line) and row['close'] < lower_line and is_short_trend: entry_signal = -1
                elif strategy_type == "RSI波段":
                    if row['RSI'] < params.get('rsi_lower', 30) and is_long_trend: entry_signal = 1
                    elif row['RSI'] > params.get('rsi_upper', 70) and is_short_trend: entry_signal = -1
                elif strategy_type == "KD波段":
                    # KD 黃金交叉/死亡交叉
                    if prev['K'] < prev['D'] and row['K'] > row['D'] and is_long_trend: entry_signal = 1
                    elif prev['K'] > prev['D'] and row['K'] < row['D'] and is_short_trend: entry_signal = -1
                elif strategy_type == "MACD波段":
                    # MACD 柱狀體翻正/翻負
                    if prev['DIF'] < prev['DEA'] and row['DIF'] > row['DEA'] and is_long_trend: entry_signal = 1
                    elif prev['DIF'] > prev['DEA'] and row['DIF'] < row['DEA'] and is_short_trend: entry_signal = -1

                if entry_signal != 0:
                    position = entry_signal; entry_price = row['close']
                    highest_high = row['high']; lowest_low = row['low']
                    target_sl = entry_price - (row['ATR'] * sl_multi) if position == 1 else entry_price + (row['ATR'] * sl_multi)
                    trades.append({'time': curr_time, 'type': 'BUY' if position == 1 else 'SELL', 'price': row['close'], 'desc': '指標訊號進場', 'cost': cost_points})

        return self.calculate_metrics(trades, cost_points), trades

    def calculate_metrics(self, trades, cost_pts):
        if not trades or len(trades) < 2: return {"狀態": "無交易", "交易次數": 0}
        profits = []
        for i in range(0, len(trades)-1, 2):
            en, ex = trades[i], trades[i+1]
            diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
            profits.append((diff - (cost_pts * 2)) * self.point_value)
        p = pd.Series(profits)
        return {"勝率": f"{len(p[p>0])/len(p):.1%}" if len(p)>0 else "0%", "淨獲利": f"{p.sum():,.0f} TWD", "交易次數": len(p), "期望值": f"{p.mean():.1f}"}
