import pandas as pd
import numpy as np

class MomentumBacktester:
    def __init__(self, df_1m):
        self.df_1m = df_1m.set_index('datetime')
        self.point_value = 10  
        self.cost = 2          

    def run_strategy(self, strategy_type, start_date, session_type="全時段", sl_multi=1.5, tp_multi=5.0, params=None):
        try:
            df = self.df_1m.loc[start_date:].copy()
        except KeyError:
            df = self.df_1m.copy()
            
        if session_type == "日盤 (08:45-13:45)":
            df = df.between_time('08:45', '13:45')
        elif session_type == "夜盤 (15:00-05:00)":
            df = df.between_time('15:00', '05:00')
            
        if df.empty: return {"狀態": "無資料", "交易次數": 0}, []

        # 設定時框 (當沖常用 5分K)
        df_5m = df.resample('5min').agg({'open':'first','high':'max','low':'min','close':'last', 'volume':'sum'}).dropna()
        for col in ['open', 'high', 'low', 'close']: df_5m[col] = df_5m[col].astype(float)

        # --- 通用指標計算 ---
        # ATR (用於移動停損)
        tr = pd.concat([df_5m['high']-df_5m['low'], (df_5m['high']-df_5m['close'].shift(1)).abs(), (df_5m['low']-df_5m['close'].shift(1)).abs()], axis=1).max(axis=1)
        df_5m['ATR'] = tr.rolling(window=14).mean().bfill()
        
        # EMA20 (輔助趨勢)
        df_5m['EMA20'] = df_5m['close'].ewm(span=20, adjust=False).mean()

        # --- 策略特定指標計算 ---
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
            
        elif strategy_type == "MACD策略":
            df_5m['EMA_fast'] = df_5m['close'].ewm(span=params['macd_fast'], adjust=False).mean()
            df_5m['EMA_slow'] = df_5m['close'].ewm(span=params['macd_slow'], adjust=False).mean()
            df_5m['DIF'] = df_5m['EMA_fast'] - df_5m['EMA_slow']
            df_5m['DEA'] = df_5m['DIF'].ewm(span=params['macd_sig'], adjust=False).mean()

        elif strategy_type == "三關價策略":
            # 需用到昨日資料，此處簡化為當日前 30 分鐘推算
            day_groups = df_5m.groupby(df_5m.index.date)
            df_5m['上關'] = np.nan
            df_5m['下關'] = np.nan
            for date, group in day_groups:
                h, l = group['high'].iloc[0], group['low'].iloc[0] # 範例用第一根K線
                df_5m.loc[group.index, '上關'] = l + (h - l) * 1.382
                df_5m.loc[group.index, '下關'] = h - (h - l) * 1.382

        # --- 回測核心邏輯 ---
        trades = []
        position = 0; entry_price = 0; target_sl = 0; highest_high = 0; lowest_low = 0

        for i in range(2, len(df_5m)):
            curr_time = df_5m.index[i]
            row = df_5m.iloc[i]; prev = df_5m.iloc[i-1]
            price = row['close']; current_atr = row['ATR']

            # 停損停利與移動追蹤 (通用)
            if position != 0:
                if position == 1:
                    highest_high = max(highest_high, row['high'])
                    target_sl = max(target_sl, highest_high - (current_atr * sl_multi))
                    if row['low'] <= target_sl:
                        trades.append({'time': curr_time, 'type': 'SELL', 'price': target_sl, 'desc': '移動停損'})
                        position = 0
                else:
                    lowest_low = min(lowest_low, row['low'])
                    target_sl = min(target_sl, lowest_low + (current_atr * sl_multi))
                    if row['high'] >= target_sl:
                        trades.append({'time': curr_time, 'type': 'BUY', 'price': target_sl, 'desc': '移動停損'})
                        position = 0
                if position != 0 and abs(price - entry_price) >= current_atr * tp_multi:
                    trades.append({'time': curr_time, 'type': 'SELL' if position == 1 else 'BUY', 'price': price, 'desc': '達標停利'})
                    position = 0

            # 進場邏輯分流
            if position == 0:
                entry_signal = 0 # 1: 多, -1: 空
                if strategy_type == "RSI當沖":
                    if row['RSI'] > params['rsi_upper'] and prev['RSI'] <= params['rsi_upper']: entry_signal = -1
                    elif row['RSI'] < params['rsi_lower'] and prev['RSI'] >= params['rsi_lower']: entry_signal = 1
                elif strategy_type == "布林通道":
                    if price > row['UB']: entry_signal = -1 # 觸頂放空
                    elif price < row['LB']: entry_signal = 1 # 觸底買進
                elif strategy_type == "MACD策略":
                    if row['DIF'] > row['DEA'] and prev['DIF'] <= prev['DEA']: entry_signal = 1
                    elif row['DIF'] < row['DEA'] and prev['DIF'] >= prev['DEA']: entry_signal = -1
                elif strategy_type == "三關價策略":
                    if price > row['上關']: entry_signal = 1
                    elif price < row['下關']: entry_signal = -1
                elif strategy_type == "箱型突破":
                    # 簡單邏輯：突破前 5 根 K 線高低點
                    box_h = df_5m['high'].iloc[max(0, i-5):i].max()
                    box_l = df_5m['low'].iloc[max(0, i-5):i].min()
                    if price > box_h: entry_signal = 1
                    elif price < box_l: entry_signal = -1

                if entry_signal != 0:
                    position = entry_signal
                    entry_price = price
                    highest_high = row['high']; lowest_low = row['low']
                    target_sl = entry_price - (current_atr * sl_multi) if position == 1 else entry_price + (current_atr * sl_multi)
                    trades.append({'time': curr_time, 'type': 'BUY' if position == 1 else 'SELL', 'price': price, 'desc': f'{strategy_type}進場'})

        return self.calculate_metrics(trades), trades

    def calculate_metrics(self, trades):
        if len(trades) % 2 != 0: trades = trades[:-1]
        if not trades: return {"狀態": "無交易", "交易次數": 0}
        profits = []
        for i in range(0, len(trades), 2):
            en, ex = trades[i], trades[i+1]
            diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
            profits.append((diff - (self.cost * 2)) * self.point_value)
        p = pd.Series(profits)
        return {"勝率": f"{len(p[p>0])/len(p):.1%}" if len(p)>0 else "0%", "累積損益": f"{p.sum():,.0f} TWD", "交易次數": len(p)}
