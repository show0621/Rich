import streamlit as st
import pandas as pd
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台動能雲端監控", layout="wide")
db = MTXDatabase()

st.title("🚀 微台指 5/15/30分 動能當沖監控 (ATR 移動停利)")

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
with col3: sl_multi = st.number_input("追蹤停損 ATR 倍數", min_value=0.5, max_value=5.0, value=2.0, step=0.1)
with col4: tp_multi = st.number_input("極限停利 ATR 倍數", min_value=1.0, max_value=20.0, value=5.0, step=0.5, help="用來吃暴漲暴跌的長K線，一般交由移動停損出場")

tester = MomentumBacktester(df_raw)
metrics, trades = tester.run_strategy(start_date=db_start, session_type=session, sl_multi=sl_multi, tp_multi=tp_multi)

st.subheader(f"📈 績效表現：{session} | 追蹤 {sl_multi}x ATR / 極限 {tp_multi}x ATR")
cols = st.columns(len(metrics))
for i, (label, val) in enumerate(metrics.items()): cols[i].metric(label, val)

st.subheader("📺 視覺化圖表：進出場與停損停利標示 (5分K)")
recent = df_raw.tail(600) 

fig = go.Figure(data=[go.Candlestick(
    x=recent['datetime'], open=recent['open'], high=recent['high'],
    low=recent['low'], close=recent['close'], name="微台 K線",
    increasing_line_color='#FF3333', increasing_fillcolor='#FF3333',
    decreasing_line_color='#00CC00', decreasing_fillcolor='#00CC00'  
)])

rangebreaks = [dict(bounds=["sat", "mon"])] 
if "日盤" in session:
    rangebreaks.append(dict(bounds=["13:45", "08:45"])) 
elif "夜盤" in session:
    rangebreaks.append(dict(bounds=["05:00", "15:00"])) 
else: 
    rangebreaks.append(dict(bounds=["05:00", "08:45"])) 
    rangebreaks.append(dict(bounds=["13:45", "15:00"])) 

if trades:
    r_start = recent['datetime'].iloc[0]
    rt = [t for t in trades if t['time'] >= r_start]
    
    # 對應新的動作描述，換上更精確的圖示
    signals = {
        '多單進場': ('triangle-up', 16, '#FF3333'),
        '空單進場': ('triangle-down', 16, '#00CC00'),
        '極限目標出場': ('star', 18, '#FFD700'),           # 吃大單邊
        '移動停利出場': ('diamond', 14, '#FF9900'),        # 賺錢出場 (橘色鑽石)
        '初始停損出場': ('x', 14, '#000000'),              # 賠錢出場 (黑色叉叉)
        '動能反轉平倉': ('square', 12, '#3366FF')
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
    hovermode='x unified'
)

st.plotly_chart(fig, use_container_width=True, theme=None)

with st.expander("📝 展開查看近期交易明細"):
    if trades:
        st.dataframe(pd.DataFrame(trades[-20:]).rename(columns={'time':'時間', 'type':'買賣', 'price':'價格', 'desc':'動作'}).set_index('時間'), use_container_width=True)
    else:
        st.write("該區間無交易紀錄。")
