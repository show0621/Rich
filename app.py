import streamlit as st
import pandas as pd
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台專業交易系統", layout="wide")
db = MTXDatabase()

st.title("🛡️ 微台指專業級當沖系統 (濾網與成本模擬)")

with st.sidebar:
    st.header("📊 系統控制")
    if st.button("📥 更新資料"):
        db.update_data(target_days=3); st.rerun()
    
    st.divider()
    strategy_mode = st.selectbox("核心策略", ["RSI當沖", "布林通道", "MACD策略", "三關價策略", "箱型突破"])
    
    st.subheader("🛠️ 進階濾網開關")
    use_trend = st.checkbox("開啟 60m EMA200 趨勢濾網", value=True)
    use_time = st.checkbox("限制黃金時段 (09:00-10:30)", value=True)
    
    st.subheader("💸 交易成本設定")
    cost_pts = st.number_input("單邊成本 (稅+費+滑價) 點數", value=3.5, step=0.5)
    
    st.divider()
    sl_multi = st.slider("移動停損 ATR", 1.0, 5.0, 1.5)
    tp_multi = st.slider("目標停利 ATR", 2.0, 15.0, 5.0)

df_raw = db.load_data()
if not df_raw.empty:
    # 策略參數
    params = {'rsi_period':14, 'rsi_upper':70, 'rsi_lower':30, 'bb_period':20, 'bb_std':2.0}
    
    tester = MomentumBacktester(df_raw)
    metrics, trades = tester.run_strategy(
        strategy_mode, "2024-01-01", "日盤 (08:45-13:45)", 
        sl_multi, tp_multi, params, 
        cost_points=cost_pts,
        use_trend_filter=use_trend,
        use_time_filter=use_time
    )
    
    cols = st.columns(len(metrics))
    for i, (k, v) in enumerate(metrics.items()): cols[i].metric(k, v)

    # 繪圖與表格 (保持不變)
    recent = df_raw.tail(500)
    fig = go.Figure(data=[go.Candlestick(x=recent['datetime'], open=recent['open'], high=recent['high'], low=recent['low'], close=recent['close'], increasing_line_color='#FF3333', decreasing_line_color='#00CC00')])
    if trades:
        rt = [t for t in trades if t['time'] >= recent['datetime'].iloc[0]]
        for t in rt:
            color = 'red' if 'BUY' in t['type'] else 'green'
            fig.add_annotation(x=t['time'], y=t['price'], text=t['desc'], showarrow=True, arrowhead=1, bgcolor=color, font=dict(color='white'))
    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📝 查看明細"):
        if trades:
            df_t = pd.DataFrame(trades).rename(columns={'time':'時間','type':'買賣','price':'價格','desc':'動作','cost':'單邊成本'})
            st.dataframe(df_t.set_index('時間'), use_container_width=True)
else:
    st.warning("請更新資料庫")
