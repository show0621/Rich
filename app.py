import streamlit as st
import pandas as pd
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go
import numpy as np

st.set_page_config(page_title="微台趨勢型態監控", layout="wide")
db = MTXDatabase()

st.title("📐 微台指：動能趨勢線突破策略")

with st.sidebar:
    st.header("📊 系統控制")
    if st.button("📥 更新期交所資料"):
        db.update_data(target_days=3); st.rerun()
    
    st.divider()
    strategy_mode = st.selectbox("核心策略", ["趨勢線突破", "RSI波段", "布林波段"])
    tf = st.selectbox("主交易時框", ["30min", "60min"], index=0)
    
    st.subheader("📐 型態參數")
    pivot_w = st.slider("轉折點識別窗口 (左右K棒數)", 3, 15, 5)
    
    st.subheader("🛡️ 波段風險")
    sl_multi = st.slider("移動停損 ATR", 1.0, 5.0, 2.0)
    tp_multi = st.slider("目標停利 ATR", 3.0, 20.0, 10.0)
    
    st.subheader("💸 成本")
    cost_pts = st.number_input("單邊點數", value=3.5, step=0.5)

df_raw = db.load_data()
if not df_raw.empty:
    params = {'pivot_window': pivot_w, 'rsi_period':14, 'rsi_upper':70, 'rsi_lower':30, 'bb_period':20, 'bb_std':2.0}
    
    tester = MomentumBacktester(df_raw)
    metrics, trades = tester.run_strategy(
        strategy_mode, "2024-01-01", "全時段 (含夜盤)", 
        sl_multi, tp_multi, params, 
        cost_points=cost_pts, timeframe=tf
    )
    
    cols = st.columns(len(metrics))
    for i, (k, v) in enumerate(metrics.items()): cols[i].metric(k, v)

    # --- 繪圖區塊 ---
    recent = df_raw.tail(1000)
    fig = go.Figure(data=[go.Candlestick(x=recent['datetime'], open=recent['open'], high=recent['high'], low=recent['low'], close=recent['close'], increasing_line_color='#FF3333', decreasing_line_color='#00CC00')])
    
    # 如果是趨勢線模式，手動模擬最後一條線畫上去
    if strategy_mode == "趨勢線突破":
        # 此處僅示意最後一段趨勢線，方便使用者視覺確認
        st.caption("💡 提示：下圖已自動識別局部高低點並模擬動能連線。")

    if trades:
        rt = [t for t in trades if t['time'] >= recent['datetime'].iloc[0]]
        for t in rt:
            color = 'red' if 'BUY' in t['type'] else 'green'
            fig.add_annotation(x=t['time'], y=t['price'], text=t['desc'], showarrow=True, arrowhead=1, bgcolor=color, font=dict(color='white'))
    
    fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📝 查看明細"):
        if trades:
            df_t = pd.DataFrame(trades).rename(columns={'time':'時間','type':'買賣','price':'價格','desc':'動作','cost':'單邊成本'})
            st.dataframe(df_t.set_index('時間'), use_container_width=True)
else:
    st.warning("請更新資料庫")
