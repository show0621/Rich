import streamlit as st
import pandas as pd
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台動能雲端監控", layout="wide")

# 初始化資料庫
db = MTXDatabase()

st.title("🚀 微台指 5/15/30分 動能當沖監控 (含停損停利)")

# 側邊欄控制
with st.sidebar:
    st.header("📊 數據控制中心")
    if st.button("🔄 更新 2024 至今數據"):
        with st.spinner("正在從 FinMind 抓取資料..."):
            if db.update_data():
                st.success("資料更新完成！")
                st.rerun()

# 讀取資料
df_raw = db.load_data()
if df_raw.empty:
    st.info("💡 目前資料庫尚無資料，請點擊左側按鈕開始更新。")
    st.stop()

# 策略參數設定
st.subheader("⚙️ 策略參數與風險管理設定")
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

with col_m1:
    mode = st.radio("回測深度", ["壓力測試(2024起)", "穩定測試(近3月)"])
with col_m2:
    session = st.selectbox("監控時段", ["全時段", "日盤 (08:45-13:45)", "夜盤 (15:00-05:00)"])
with col_m3:
    sl_points = st.number_input("強制停損點數", min_value=10, max_value=100, value=20, step=5)
with col_m4:
    tp_points = st.number_input("強制停利點數", min_value=10, max_value=200, value=40, step=5)

start_dt = "2024-01-01" if "壓力測試" in mode else (pd.Timestamp.now() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')

# 執行策略
tester = MomentumBacktester(df_raw)
metrics, trades = tester.run_strategy(start_dt, session_type=session, sl_points=sl_points, tp_points=tp_points)

# 顯示績效
st.subheader(f"📈 績效表現：{session} | 停損 {sl_points}點 / 停利 {tp_points}點")
cols = st.columns(len(metrics))
for i, (label, val) in enumerate(metrics.items()):
    cols[i].metric(label, val)

# 畫出即時監控 K 線與視覺化進出場
st.subheader("📺 視覺化圖表：進出場與停損停利標示")
recent = df_raw.tail(300) # 顯示最近 300 根 1分K
fig = go.Figure()

# 畫 K 線
fig.add_trace(go.Candlestick(
    x=recent['datetime'], open=recent['open'], high=recent['high'],
    low=recent['low'], close=recent['close'], name="微台 K線"
))

# 標示交易訊號
if trades:
    recent_start = recent['datetime'].iloc[0]
    recent_trades = [t for t in trades if t['time'] >= recent_start]
    
    # 分類交易紀錄
    long_en = [t for t in recent_trades if t['desc'] == '多單進場']
    short_en = [t for t in recent_trades if t['desc'] == '空單進場']
    tp_ex = [t for t in recent_trades if t['desc'] == '停利出場']
    sl_ex = [t for t in recent_trades if t['desc'] == '停損出場']
    rev_ex = [t for t in recent_trades if t['desc'] == '反轉平倉']

    # 多單進場 (紅色向上箭頭)
    if long_en:
        fig.add_trace(go.Scatter(x=[t['time'] for t in long_en], y=[t['price'] for t in long_en], mode='markers', marker=dict(symbol='triangle-up', size=14, color='red'), name='多單進場'))
    # 空單進場 (綠色向下箭頭)
    if short_en:
        fig.add_trace(go.Scatter(x=[t['time'] for t in short_en], y=[t['price'] for t in short_en], mode='markers', marker=dict(symbol='triangle-down', size=14, color='green'), name='空單進場'))
    # 停利 (黃金星星)
    if tp_ex:
        fig.add_trace(go.Scatter(x=[t['time'] for t in tp_ex], y=[t['price'] for t in tp_ex], mode='markers', marker=dict(symbol='star', size=14, color='gold'), name='停利出場'))
    # 停損 (白色叉叉)
    if sl_ex:
        fig.add_trace(go.Scatter(x=[t['time'] for t in sl_ex], y=[t['price'] for t in sl_ex], mode='markers', marker=dict(symbol='x', size=12, color='white'), name='停損出場'))
    # 反轉平倉 (藍色方塊)
    if rev_ex:
        fig.add_trace(go.Scatter(x=[t['time'] for t in rev_ex], y=[t['price'] for t in rev_ex], mode='markers', marker=dict(symbol='square', size=10, color='blue'), name='反轉平倉'))

fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

# 顯示近期交易明細清單
with st.expander("📝 展開查看近期交易明細"):
    if trades:
        df_trades = pd.DataFrame(trades[-20:]) # 顯示最後 20 筆
        df_trades = df_trades.rename(columns={'time':'時間', 'type':'買賣', 'price':'價格', 'desc':'動作說明'})
        st.dataframe(df_trades.set_index('時間'), use_container_width=True)
    else:
        st.write("該區間無交易紀錄。")
