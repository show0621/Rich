import streamlit as st
import pandas as pd
import numpy as np
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台多策略監控", layout="wide")
db = MTXDatabase()

# ================= 1. 新增：大盤狀態探測函式 =================
def detect_market_regime(df_1m):
    """
    利用 RSI 策略近期的勝率表現，反推現在的市場狀態。
    """
    if df_1m.empty or len(df_1m) < 300:
        return "資料不足", "gray"
        
    # 取最近約 300 根 1分K (約一天的交易量) 來測風向
    recent_df = df_1m.tail(300)
    # 使用一個中性的 RSI 參數進行背景盲測
    radar_tester = MomentumBacktester(recent_df)
    radar_params = {'rsi_period': 14, 'rsi_upper': 70, 'rsi_lower': 30}
    
    # 執行一次快速回測
    _, trades = radar_tester.run_strategy(
        "RSI當沖", 
        recent_df.index[0], 
        "全時段", 
        sl_multi=1.0, 
        tp_multi=2.0, 
        params=radar_params
    )
    
    if not trades or len(trades) < 4:
        return "波動過低 (無訊號)", "gray"
        
    # 計算最近幾筆交易的盈虧狀況
    profits = []
    for i in range(0, len(trades)-1, 2):
        en, ex = trades[i], trades[i+1]
        diff = (ex['price'] - en['price']) if en['type'] == 'BUY' else (en['price'] - ex['price'])
        profits.append(diff)
        
    win_rate = len([p for p in profits if p > 0]) / len(profits)
    
    if win_rate >= 0.6:
        return "震盪盤 (適合 RSI/布林)", "green"
    elif win_rate <= 0.4:
        return "趨勢盤 (適合 突破/MACD)", "red"
    else:
        return "混沌不明 (觀望為宜)", "orange"

# ================= 2. 主程式介面 =================
st.title("🚀 微台指多因子當沖戰情室")

# 預先讀取資料以便雷達運作
df_raw = db.load_data()

with st.sidebar:
    st.header("📊 系統控制")
    if st.button("📥 更新期交所資料"):
        with st.spinner("資料同步中..."):
            db.update_data(target_days=3)
            st.rerun()
    
    # 📡 插入大盤狀態雷達
    if not df_raw.empty:
        regime, color = detect_market_regime(df_raw)
        st.divider()
        st.markdown(f"### 📡 盤勢雷達: :{color}[**{regime}**]")
        st.caption("偵測邏輯：利用 RSI 近期盲測勝率反推市場慣性。")
    
    st.divider()
    strategy_mode = st.selectbox("選擇交易策略", ["RSI當沖", "布林通道", "MACD策略", "三關價策略", "箱型突破"])
    session = st.selectbox("時段", ["全時段", "日盤 (08:45-13:45)", "夜盤 (15:00-05:00)"])
    
    st.subheader("🛡️ 風控設定 (ATR)")
    sl_multi = st.slider("移動停損 ATR 倍數", 1.0, 5.0, 1.5, 0.1)
    tp_multi = st.slider("目標停利 ATR 倍數", 2.0, 10.0, 4.0, 0.5)

# 策略參數動態介面
params = {}
st.subheader(f"⚙️ {strategy_mode} 參數微調")
c1, c2, c3 = st.columns(3)
if strategy_mode == "RSI當沖":
    with c1: params['rsi_period'] = st.number_input("RSI週期", 5, 30, 14)
    with c2: params['rsi_upper'] = st.slider("超買界線", 60, 90, 70)
    with c3: params['rsi_lower'] = st.slider("超賣界線", 10, 40, 30)
elif strategy_mode == "布林通道":
    with c1: params['bb_period'] = st.number_input("均線週期", 10, 60, 20)
    with c2: params['bb_std'] = st.slider("標準差倍數", 1.5, 3.0, 2.0, 0.1)
elif strategy_mode == "MACD策略":
    with c1: params['macd_fast'] = st.number_input("快線", 5, 20, 12)
    with c2: params['macd_slow'] = st.number_input("慢線", 21, 40, 26)
    with c3: params['macd_sig'] = st.number_input("訊號線", 5, 15, 9)
else:
    st.info("此策略使用系統預設動態參數")

# 執行回測
if not df_raw.empty:
    tester = MomentumBacktester(df_raw)
    # 預設從 2024 年開始回測，確保資料庫有足夠長度
    metrics, trades = tester.run_strategy(strategy_mode, "2024-01-01", session, sl_multi, tp_multi, params)
    
    # 績效看板
    cols = st.columns(len(metrics))
    for i, (k, v) in enumerate(metrics.items()): cols[i].metric(k, v)

    # 繪圖
    recent = df_raw.tail(500)
    fig = go.Figure(data=[go.Candlestick(
        x=recent['datetime'], 
        open=recent['open'], 
        high=recent['high'], 
        low=recent['low'], 
        close=recent['close'], 
        increasing_line_color='#FF3333', 
        decreasing_line_color='#00CC00'
    )])
    
    # 標記進出場
    if trades:
        rt = [t for t in trades if t['time'] >= recent['datetime'].iloc[0]]
        for t in rt:
            color = 'red' if 'BUY' in t['type'] else 'green'
            fig.add_annotation(
                x=t['time'], 
                y=t['price'], 
                text=t['desc'], 
                showarrow=True, 
                arrowhead=1, 
                bgcolor=color, 
                font=dict(color='white')
            )

    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
    
    # ================= 歷史明細與 CSV 下載區塊 =================
    st.divider()
    st.subheader("📝 歷史成交明細與匯出")
    
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades = df_trades.rename(columns={'time': '時間', 'type': '買賣', 'price': '價格', 'desc': '動作'})
        df_trades['時間'] = pd.to_datetime(df_trades['時間']).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        st.dataframe(df_trades.set_index('時間'), use_container_width=True)
        
        csv = df_trades.to_csv(index=False, encoding='utf-8-sig') 
        st.download_button(
            label="📥 下載完整交易紀錄 (CSV 檔)",
            data=csv,
            file_name=f"MTX_trades_{strategy_mode}.csv",
            mime="text/csv"
        )
    else:
        st.write("該區間無交易紀錄。")
else:
    st.warning("請先更新資料庫")
