import streamlit as st
import pandas as pd
import numpy as np
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台趨勢型態監控", layout="wide")
db = MTXDatabase()

# ================= 1. 盤勢雷達核心函式 (修復版) =================
def detect_market_regime(df_1m):
    """
    利用近期 RSI 表現反推市場狀態。
    """
    if df_1m.empty or len(df_1m) < 300:
        return "資料不足", "gray"
        
    recent_df = df_1m.tail(300).copy()
    start_time_val = recent_df['datetime'].iloc[0]
    
    radar_tester = MomentumBacktester(recent_df)
    # 使用標準參數進行盲測
    radar_params = {'rsi_period': 14, 'rsi_upper': 70, 'rsi_lower': 30}
    
    try:
        # 注意：這裡的策略名稱需與 backtest.py 裡的 "RSI波段" 一致
        _, trades = radar_tester.run_strategy(
            "RSI波段", 
            start_time_val, 
            "全時段", 
            params=radar_params,
            timeframe='5min' # 雷達用短時框探測靈敏度
        )
        
        if not trades or len(trades) < 4:
            return "波動過低 (無訊號)", "gray"
            
        profits = []
        for i in range(0, len(trades)-1, 2):
            en, ex = trades[i], trades[i+1]
            diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
            profits.append(diff)
            
        win_rate = len([p for p in profits if p > 0]) / len(profits)
        
        if win_rate >= 0.6:
            return "震盪盤 (適合 RSI/布林)", "green"
        elif win_rate <= 0.4:
            return "趨勢盤 (適合 趨勢線/突破)", "red"
        else:
            return "混沌不明 (觀望為宜)", "orange"
    except Exception as e:
        return "雷達校準中...", "gray"

# ================= 2. 主程式介面 =================
st.title("📐 微台指：動能趨勢線與盤勢監控")

df_raw = db.load_data()

with st.sidebar:
    st.header("📊 系統控制")
    if st.button("📥 更新期交所資料"):
        with st.spinner("資料同步中..."):
            db.update_data(target_days=3)
            st.rerun()
    
    # 📡 重新上線：盤勢雷達
    regime = "資料不足"
    color = "gray"
    if not df_raw.empty:
        regime, color = detect_market_regime(df_raw)
        st.divider()
        st.markdown(f"### 📡 盤勢雷達: :{color}[**{regime}**]")
        st.caption("偵測邏輯：利用 RSI 近期盲測勝率反推市場慣性。")
    
    st.divider()
    strategy_mode = st.selectbox("核心策略", ["趨勢線突破", "RSI波段", "布林波段"])
    tf = st.selectbox("主交易時框", ["30min", "60min", "15min", "5min"], index=0)
    
    st.divider()
    st.subheader("🛡️ 風控與參數建議")
    
    # 💡 重新上線：自動參數建議邏輯
    if regime == "震盪盤 (適合 RSI/布林)":
        st.info("💡 建議：切換至 RSI 或布林策略。縮短停損 (1.2x - 1.5x ATR)，採固定目標停利。")
    elif regime == "趨勢盤 (適合 趨勢線/突破)":
        st.warning("💡 建議：優先使用趨勢線策略。放寬停損 (2.0x+ ATR)，讓利潤奔跑。")
    elif regime == "混沌不明 (觀望為宜)":
        st.info("💡 建議：盤勢不明，建議將『轉折窗口』調大，過濾雜訊。")

    sl_multi = st.slider("移動停損 ATR 倍數", 1.0, 5.0, 2.0, 0.1)
    tp_multi = st.slider("目標停利 ATR 倍數", 3.0, 20.0, 10.0, 0.5)
    
    st.divider()
    st.subheader("💸 成本與型態設定")
    pivot_w = st.slider("轉折點識別窗口", 3, 15, 5)
    cost_pts = st.number_input("單邊成本點數", value=3.5, step=0.5)

# ================= 3. 執行回測與繪圖 =================
if not df_raw.empty:
    params = {
        'pivot_window': pivot_w, 
        'rsi_period': 14, 
        'rsi_upper': 70, 
        'rsi_lower': 30, 
        'bb_period': 20, 
        'bb_std': 2.0
    }
    
    tester = MomentumBacktester(df_raw)
    metrics, trades = tester.run_strategy(
        strategy_mode, "2024-01-01", "全時段 (含夜盤)", 
        sl_multi, tp_multi, params, 
        cost_points=cost_pts, timeframe=tf
    )
    
    # 績效看板
    cols = st.columns(len(metrics))
    for i, (k, v) in enumerate(metrics.items()):
        cols[i].metric(k, v)

    # 繪圖
    recent = df_raw.tail(1000)
    fig = go.Figure(data=[go.Candlestick(
        x=recent['datetime'], 
        open=recent['open'], 
        high=recent['high'], 
        low=recent['low'], 
        close=recent['close'], 
        increasing_line_color='#FF3333', 
        decreasing_line_color='#00CC00'
    )])
    
    if trades:
        rt = [t for t in trades if t['time'] >= recent['datetime'].iloc[0]]
        for t in rt:
            color = 'red' if 'BUY' in t['type'] else 'green'
            fig.add_annotation(
                x=t['time'], y=t['price'], text=t['desc'], 
                showarrow=True, arrowhead=1, bgcolor=color, font=dict(color='white')
            )

    fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # 歷史明細與下載
    st.divider()
    if trades:
        df_trades = pd.DataFrame(trades).rename(columns={'time': '時間', 'type': '買賣', 'price': '價格', 'desc': '動作'})
        df_trades['時間'] = pd.to_datetime(df_trades['時間']).dt.strftime('%Y-%m-%d %H:%M:%S')
        st.dataframe(df_trades.set_index('時間'), use_container_width=True)
        
        csv = df_trades.to_csv(index=False, encoding='utf-8-sig') 
        st.download_button(label="📥 下載完整交易紀錄 (CSV 檔)", data=csv, file_name=f"MTX_{strategy_mode}.csv", mime="text/csv")
    else:
        st.write("該區間目前無交易訊號，請試著縮小『轉折窗口』或『切換時框』。")
else:
    st.warning("請更新資料庫")
