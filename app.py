import streamlit as st
import pandas as pd
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台動能雲端監控", layout="wide")
db = MTXDatabase()

st.title("🚀 微台指 5/15/30分 動能當沖監控 (真實期交所資料)")

with st.sidebar:
    st.header("📊 數據控制中心")
    st.write("點擊下方按鈕，系統會自動抓取最新資料並**疊加累積**到資料庫中。")
    if st.button("📥 抓取最新資料並寫入資料庫"):
        with st.spinner("正從期交所下載逐筆資料並轉譯中 (約需 10 秒)..."):
            if db.update_data(target_days=3):
                st.success("✅ 真實資料已成功疊加至資料庫！")
                st.rerun()
            else:
                st.error("❌ 更新失敗，可能是假日無新資料。")

df_raw = db.load_data()
if df_raw.empty:
    st.info("💡 目前資料庫尚無資料，請點擊左側按鈕開始向期交所索取真實資料。")
    st.stop()

st.subheader("⚙️ 策略參數與風險管理設定")
col1, col2, col3, col4 = st.columns(4)
with col1: 
    db_start = df_raw['datetime'].iloc[0].strftime('%Y-%m-%d')
    db_end = df_raw['datetime'].iloc[-1].strftime('%Y-%m-%d')
    mode = st.radio("回測資料庫範圍", [f"{db_start} 至 {db_end}"])
with col2: session = st.selectbox("監控時段", ["全時段", "日盤 (08:45-13:45)", "夜盤 (15:00-05:00)"])
with col3: sl_points = st.number_input("強制停損點數", min_value=10, max_value=100, value=20, step=5)
with col4: tp_points = st.number_input("強制停利點數", min_value=10, max_value=200, value=40, step=5)

tester = MomentumBacktester(df_raw)
metrics, trades = tester.run_strategy(start_date=db_start, session_type=session, sl_points=sl_points, tp_points=tp_points)

st.subheader(f"📈 績效表現：{session} | 停損 {sl_points}點 / 停利 {tp_points}點")
cols = st.columns(len(metrics))
for i, (label, val) in enumerate(metrics.items()): cols[i].metric(label, val)

st.subheader("📺 視覺化圖表：進出場與停損停利標示 (5分K)")
recent = df_raw.tail(600) 

# 🎨 1. K線在地化配色：改為台灣習慣的「紅漲綠跌」
fig = go.Figure(data=[go.Candlestick(
    x=recent['datetime'], open=recent['open'], high=recent['high'],
    low=recent['low'], close=recent['close'], name="微台 K線",
    increasing_line_color='#FF3333', increasing_fillcolor='#FF3333', # 紅漲
    decreasing_line_color='#00CC00', decreasing_fillcolor='#00CC00'  # 綠跌
)])

# ✂️ 2. 斷點縫合魔法：根據選擇的時段，裁掉沒有交易的時間
rangebreaks = [dict(bounds=["sat", "mon"])] # 永遠隱藏週末
if "日盤" in session:
    rangebreaks.append(dict(bounds=["13:45", "08:45"])) # 隱藏 13:45 到隔天 08:45
elif "夜盤" in session:
    rangebreaks.append(dict(bounds=["05:00", "15:00"])) # 隱藏 05:00 到下午 15:00
else: # 全時段
    rangebreaks.append(dict(bounds=["05:00", "08:45"])) # 隱藏早上的休息空檔
    rangebreaks.append(dict(bounds=["13:45", "15:00"])) # 隱藏下午的休息空檔

# 標記進出場訊號
if trades:
    r_start = recent['datetime'].iloc[0]
    rt = [t for t in trades if t['time'] >= r_start]
    
    signals = {
        '多單進場': ('triangle-up', 16, '#FF3333'),
        '空單進場': ('triangle-down', 16, '#00CC00'),
        '停利出場': ('star', 18, '#FFD700'),
        '停損出場': ('x', 14, '#000000'), 
        '反轉平倉': ('square', 12, '#3366FF')
    }
    for desc, (sym, size, color) in signals.items():
        subset = [t for t in rt if t['desc'] == desc]
        if subset:
            fig.add_trace(go.Scatter(
                x=[t['time'] for t in subset], y=[t['price'] for t in subset],
                mode='markers', 
                marker=dict(symbol=sym, size=size, color=color, line=dict(width=1.5, color='white' if sym=='x' else 'black')), 
                name=desc
            ))

# 🌟 3. 版面精緻化：加入無縫 X 軸、優化網格線
fig.update_xaxes(
    rangebreaks=rangebreaks, 
    showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)', zeroline=False
)
fig.update_yaxes(
    showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)', zeroline=False
)
fig.update_layout(
    height=700, 
    xaxis_rangeslider_visible=False,
    margin=dict(l=40, r=40, t=40, b=40),
    hovermode='x unified' # 滑鼠游標對齊效果
)

# 讓 Streamlit 接管背景主題，完美融入您的系統
st.plotly_chart(fig, use_container_width=True)

with st.expander("📝 展開查看近期交易明細"):
    if trades:
        st.dataframe(pd.DataFrame(trades[-20:]).rename(columns={'time':'時間', 'type':'買賣', 'price':'價格', 'desc':'動作'}).set_index('時間'), use_container_width=True)
    else:
        st.write("該區間無交易紀錄。")
