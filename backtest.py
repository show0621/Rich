import pandas as pd
import numpy as np

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  
        # 成本預設改為動態參數傳入

    def run_strategy(self, strategy_type, start_date, session_type="全時段", 
                     sl_multi=1.5, tp_multi=5.0, params=None, 
                     cost_points=3.5, # 包含稅+費+滑價的總合點數
                     use_trend_filter=True, 
                     use_time_filter=True):
        
        try:
            df = self.df_1m.loc[start_date:].copy()
        except KeyError:
            df = self.df_1m.copy()
            
        if session_type == "日盤 (08:45-13:45)":
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        # --- 多時框濾網計算 (60分鐘 EMA200) ---
        df_60m = df.resample('60min').agg({'close':'last'}).dropna()
        df_60m['EMA200_60m'] = df_60m['close'].ewm(span=200, adjust=False).mean()
        # 將長線指標對應回短線 K 線
        df_trend = df_60m[['EMA200_60m']].reindex(df.index, method='ffill')

        # --- 短線 5分鐘指標計算 ---
        df_5m = df.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last', 'volume':'sum'}).dropna()
        for col in ['open', 'high', 'low', 'close']: df_5m[col] = df_5m[col].astype(float)
        
        df_5m = df_5m.join(df_trend) # 合併趨勢濾網

        # ATR 與 RSI 等通用指標
        tr = pd.concat([df_5m['high']-df_5m['low'], (df_5m['high']-df_5m['close'].shift(1)).abs(), (df_5m['low']-df_5m['close'].shift(1)).abs()], axis=1).max(axis=1)
        df_5m['ATR'] = tr.rolling(window=14).mean().bfill()
        df_5m['VOL_MA'] = df_5m['volume'].rolling(window=10).mean() # 量價濾網用

        if strategy_type == "RSI當沖":
            diff = df_5m['close'].diff()
            up, down = diff.where(diff > 0, 0.0), -diff.where(diff < 0, 0.0)
            ema_up, ema_down = up.ewm(alpha=1/params['rsi_period'], adjust=False).mean(), down.ewm(alpha=1/params['rsi_period'], adjust=False).mean()
            df_5m['RSI'] = 100 - (100 / (1 + ema_up / ema_down))
        elif strategy_type == "布林通道":
            df_5m['MA'] = df_5m['close'].rolling(window=params['bb_period']).mean()
            df_5m['std'] = df_5m['close'].rolling(window=params['bb_period']).std()
            df_5m['UB'] = df_5m['MA'] + params['bb_std'] * df_5m['std']
            df_5m['LB'] = df_5m['MA'] - params['bb_std'] * df_5m['std']

        # --- 回測核心邏輯 ---
        trades = []
        position = 0; entry_price = 0; target_sl = 0; highest_high = 0; lowest_low = 0

        for i in range(2, len(df_5m)):
            curr_time = df_5m.index[i]
            row = df_5m.iloc[i]; prev = df_5m.iloc[i-1]
            price = row['close']

            # 1. 停損停利邏輯 (不變)
            if position != 0:
                if position == 1:
                    highest_high = max(highest_high, row['high'])
                    target_sl = max(target_sl, highest_high - (row['ATR'] * sl_multi))
                    if row['low'] <= target_sl:
                        trades.append({'time': curr_time, 'type': 'SELL', 'price': target_sl, 'desc': '移動停損', 'cost': cost_points})
                        position = 0
                else:
                    lowest_low = min(lowest_low, row['low'])
                    target_sl = min(target_sl, lowest_low + (row['ATR'] * sl_multi))
                    if row['high'] >= target_sl:
                        trades.append({'time': curr_time, 'type': 'BUY', 'price': target_sl, 'desc': '移動停損', 'cost': cost_points})
                        position = 0
                if position != 0 and abs(price - entry_price) >= row['ATR'] * tp_multi:
                    trades.append({'time': curr_time, 'type': 'SELL' if position == 1 else 'BUY', 'price': price, 'desc': '達標停利', 'cost': cost_points})
                    position = 0

            # 2. 進場邏輯 (加入時段、趨勢與量價濾網)
            if position == 0:
                # [時段濾網] 僅在 09:00 - 10:30 尋找進場點
                if use_time_filter:
                    if not (curr_time.hour == 9 or (curr_time.hour == 10 and curr_time.minute <= 30)):
                        continue

                entry_signal = 0 
                # [趨勢濾網] 判斷長線方向
                is_long_trend = price > row['EMA200_60m'] if use_trend_filter else True
                is_short_trend = price < row['EMA200_60m'] if use_trend_filter else True

                if strategy_type == "RSI當沖":
                    if row['RSI'] < params['rsi_lower'] and prev['RSI'] >= params['rsi_lower'] and is_long_trend:
                        entry_signal = 1
                    elif row['RSI'] > params['rsi_upper'] and prev['RSI'] <= params['rsi_upper'] and is_short_trend:
                        entry_signal = -1
                
                elif strategy_type == "布林通道":
                    # [量價濾網] 觸頂且成交量萎縮，代表反轉機會高
                    if price > row['UB'] and row['volume'] < row['VOL_MA'] and is_short_trend:
                        entry_signal = -1
                    elif price < row['LB'] and row['volume'] < row['VOL_MA'] and is_long_trend:
                        entry_signal = 1

                if entry_signal != 0:
                    position = entry_signal; entry_price = price
                    highest_high = row['high']; lowest_low = row['low']
                    target_sl = entry_price - (row['ATR'] * sl_multi) if position == 1 else entry_price + (row['ATR'] * sl_multi)
                    trades.append({'time': curr_time, 'type': 'BUY' if position == 1 else 'SELL', 'price': price, 'desc': f'{strategy_type}進場', 'cost': cost_points})

        return self.calculate_metrics(trades, cost_points), trades

    def calculate_metrics(self, trades, cost_per_side):
        if len(trades) % 2 != 0: trades = trades[:-1]
        if not trades: return {"狀態": "無交易", "交易次數": 0}
        profits = []
        for i in range(0, len(trades), 2):
            en, ex = trades[i], trades[i+1]
            # 每趟交易扣除兩次手續費與滑價 (進+出)
            total_cost_points = cost_per_side * 2
            diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
            net_profit_points = diff - total_cost_points
            profits.append(net_profit_points * self.point_value)
        p = pd.Series(profits)
        return {
            "勝率": f"{len(p[p>0])/len(p):.1%}" if len(p)>0 else "0%",
            "淨獲利 (已扣成本)": f"{p.sum():,.0f} TWD",
            "交易次數": len(p),
            "平均每筆淨利": f"{p.mean():.1f} TWD"
        }
