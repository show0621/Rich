import streamlit as st
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台動能監控系統", layout="wide")

db = MTXDatabase()

# 側邊欄控制
st.sidebar.title("🛠 系統控制")
if st.sidebar.button("更新最新資料並寫入資料庫"):
    if db.update_data():
        st.sidebar.success("資料更新成功！")

df_raw = db.load_data()
tester = MomentumBacktester(df_raw)

# 測試層次選擇
st.title("📊 微台指動能策略分析與監控")
mode = st.radio("選擇回測層次", ["壓力測試 (2024至今)", "穩定性測試 (最近3個月)"])

if mode == "壓力測試 (2024至今)":
    results = tester.run_strategy("2024-01-01", "2026-12-31")
else:
    results = tester.run_strategy("2026-01-27", "2026-04-27") # 以今日為基準回推3個月

# 顯示績效指標
cols = st.columns(4)
for i, (k, v) in enumerate(results.items()):
    cols[i%4].metric(k, v)

# 畫出即時監控圖表 (示例 5分K)
st.subheader("📡 即時動能監控 (5分鐘 K線)")
fig = go.Figure(data=[go.Candlestick(x=df_raw['datetime'].tail(100),
                open=df_raw['open'].tail(100), high=df_raw['high'].tail(100),
                low=df_raw['low'].tail(100), close=df_raw['close'].tail(100))])
st.plotly_chart(fig, use_container_width=True)
