import streamlit as st
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台動能雲端監控", layout="wide")

db = MTXDatabase()

st.title("📈 微台指 5/15/30分 動能當沖監控")

# 1. 側邊欄：資料更新
with st.sidebar:
    st.header("數據管理")
    if st.button("🔄 更新 2024 至今數據"):
        with st.spinner("更新中..."):
            db.update_data()
            st.success("資料庫已就緒")

# 2. 資料加載
df_raw = db.load_data()
if df_raw.empty:
    st.warning("請點擊左側更新數據以啟動系統。")
    st.stop()

# 3. 回測模式切換
mode = st.radio("選擇分析模式", ["壓力測試 (2024至今)", "穩定性測試 (最近3個月)"], horizontal=True)
start_date = "2024-01-01" if "壓力測試" in mode else "2026-01-27"

# 4. 執行計算
tester = MomentumBacktester(df_raw)
metrics = tester.run_strategy(start_date)

# 5. 顯示數據指標
st.subheader(f"📊 策略表現：{mode}")
m_cols = st.columns(len(metrics))
for i, (label, value) in enumerate(metrics.items()):
    m_cols[i].metric(label, value)

# 6. 即時 K 線圖
st.subheader("📺 5分鐘 K線動能監控")
recent_df = df_raw.tail(150)
fig = go.Figure(data=[go.Candlestick(
    x=recent_df['datetime'],
    open=recent_df['open'], high=recent_df['high'],
    low=recent_df['low'], close=recent_df['close'],
    name="MTX"
)])
fig.update_layout(height=500, template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)
