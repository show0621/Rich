import streamlit as st
import pandas as pd
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台動能監控系統", layout="wide")

# 初始化資料庫
db = MTXDatabase()

st.title("🚀 微台指 5/15/30分 動能當沖策略監控")

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

# 檢查資料庫是否為空
if df_raw.empty:
    st.info("💡 目前資料庫尚無資料，請點擊左側按鈕開始更新。")
    st.stop()

# 模式選擇
mode = st.radio("回測模式", ["壓力測試 (2024至今)", "穩定性測試 (最近3個月)"], horizontal=True)
start_dt = "2024-01-01" if "壓力測試" in mode else (pd.Timestamp.now() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')

# 執行策略
tester = MomentumBacktester(df_raw)
metrics = tester.run_strategy(start_dt)

# 顯示績效
st.subheader(f"📈 績效表現：{mode}")
cols = st.columns(len(metrics))
for i, (label, val) in enumerate(metrics.items()):
    cols[i].metric(label, val)

# 畫出即時監控 K 線
st.subheader("📺 即時監控儀表板 (5分鐘 K線)")
recent = df_raw.tail(200)
fig = go.Figure(data=[go.Candlestick(
    x=recent['datetime'],
    open=recent['open'], high=recent['high'],
    low=recent['low'], close=recent['close']
)])
fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)
