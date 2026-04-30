import streamlit as st
import pandas as pd
import numpy as np
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台全功能回測戰情室", layout="wide")
db = MTXDatabase()

# --- 盤勢偵測雷達 ---
def detect_market_regime(df_raw):
    if df_raw.empty or len(df_raw) < 500: return "資料不足", "gray"
    test_df = df_raw.tail(500).copy()
    start_t = test_df['datetime'].iloc[0]
    tester = MomentumBacktester(test_df)
    res, trades = tester.run_strategy("RSI波段", start_t, timeframe='15min', params={'rsi_period':14, 'rsi_upper':70, 'rsi_lower':30})
    if res['交易次數'] < 3: return "波動過低", "gray"
    win_rate = float(res['勝率'].replace('%',''))
    if win_rate >= 55: return "震盪盤 (適合 RSI/KD)", "green"
    elif win_rate <= 40: return "趨勢盤 (適合 趨勢線/MACD)", "red"
    return "市場混沌", "orange"

st.title("🛡️ 微台指：全功能指標與時段回測系統")

df_raw = db.load_data()

with st.sidebar:
    st.header("📊 系統控制")
    if st.button("📥 更新期交所資料"):
        with st.spinner("同步中..."): db.update_data(target_days=3); st.rerun()
    
    regime = "資料不足"; color = "gray"
    if not df_raw.empty:
        regime, color = detect_market_regime(df_raw)
        st.divider()
        st.markdown(f"### 📡 盤勢雷達: :{color}[**{regime}**]")
    
    st.divider()
    strategy_mode = st.selectbox("策略選擇", ["趨勢線突破", "RSI波段", "KD波段", "MACD波段"])
    session = st.selectbox("時段選擇", ["全時段", "日盤 (08:45-13:45)", "夜盤 (15:00-05:00)"])
    tf = st.selectbox("主交易時框", ["30min", "60min", "15min", "5min"], index=0)
    
    st.divider()
    st.subheader("⚙️ 策略參數")
    p_win = 5; v_mul = 1.2; r_period = 14; kd_p = 9; m_fast = 12; m_slow = 26; m_sig = 9

    if strategy_mode == "趨勢線突破":
        p_win = st.slider("轉折窗口", 3, 15, 5)
        v_mul = st.slider("量能爆發倍數", 1.0, 3.0, 1.2)
    elif strategy_mode == "KD波段":
        kd_p = st.number_input("KD 週期", 5, 20, 9)
    elif strategy_mode == "MACD波段":
        m_fast = st.number_input("快線", 5, 20, 12)
        m_slow = st.number_input("慢線", 21, 40, 26)
        m_sig = st.number_input("訊號線", 5, 15, 9)

    st.subheader("🛡️ 風控設定")
    sl_m = st.slider("移動停損 ATR", 1.0, 5.0, 2.0)
    tp_m = st.slider("目標停利 ATR", 3.0, 20.0, 10.0)
    cost_p = st.number_input("單邊成本", value=3.5, step=0.5)

# --- 執行回測 ---
if not df_raw.empty:
    tester = MomentumBacktester(df_raw)
    params = {
        'pivot_window': p_win, 'volume_multi': v_mul, 
        'rsi_period': r_period, 'rsi_upper': 70, 'rsi_lower': 30,
        'kd_period': kd_p, 'macd_fast': m_fast, 'macd_slow': m_slow, 'macd_sig': m_sig
    }
    
    metrics, trades = tester.run_strategy(
        strategy_mode, "2024-01-01", session, 
        sl_m, tp_m, params, cost_points=cost_p, timeframe=tf
    )
    
    # 績效看板
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("勝率", metrics.get("勝率", "0%"))
    c2.metric("淨獲利", metrics.get("淨獲利", "0 TWD"))
    c3.metric("交易次數", metrics.get("交易次數", 0))
    c4.metric("期望值", metrics.get("期望值", "0"))

    # 繪圖
    recent = df_raw.tail(1000)
    fig = go.Figure(data=[go.Candlestick(x=recent['datetime'], open=recent['open'], high=recent['high'], low=recent['low'], close=recent['close'], increasing_line_color='#FF3333', decreasing_line_color='#00CC00')])
    
    if trades:
        rt = [t for t in trades if t['time'] >= recent['datetime'].iloc[0]]
        for t in rt:
            fig.add_annotation(x=t['time'], y=t['price'], text=t['desc'], showarrow=True, arrowhead=1, bgcolor='red' if 'BUY' in t['type'] else 'green', font=dict(color='white'))

    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📝 明細與下載"):
        if trades:
            df_t = pd.DataFrame(trades)
            st.dataframe(df_t.set_index('time'), use_container_width=True)
            st.download_button("📥 下載 CSV", df_t.to_csv(index=False, encoding='utf-8-sig'), f"MTX_{strategy_mode}.csv", "text/csv")
else:
    st.warning("請更新資料庫")
