import streamlit as st
import pandas as pd
import numpy as np
from database import MTXDatabase
from backtest import MomentumBacktester
import plotly.graph_objects as go

st.set_page_config(page_title="微台專業型態戰情室", layout="wide")
db = MTXDatabase()

# --- 盤勢偵測雷達 ---
def detect_market_regime(df_raw):
    if df_raw.empty or len(df_raw) < 500: return "資料不足", "gray"
    # 使用 15分K RSI 盲測最近勝率
    test_df = df_raw.tail(500).copy()
    start_t = test_df['datetime'].iloc[0] # 修復索引錯誤
    tester = MomentumBacktester(test_df)
    res, trades = tester.run_strategy("RSI波段", start_t, timeframe='15min', params={'rsi_period':14, 'rsi_upper':70, 'rsi_lower':30})
    
    if res['交易次數'] < 3: return "波動過低", "gray"
    win_rate = float(res['勝率'].replace('%',''))
    if win_rate >= 55: return "震盪盤 (適合 RSI)", "green"
    elif win_rate <= 40: return "趨勢盤 (適合 趨勢線突破)", "red"
    return "市場混沌", "orange"

st.title("🛡️ 微台指：動態趨勢線與量能監控系統")

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
    strategy_mode = st.selectbox("策略選擇", ["趨勢線突破", "RSI波段"])
    tf = st.selectbox("主交易時框", ["30min", "60min", "15min", "5min"], index=0)
    
    st.subheader("📐 進階參數")
    p_win = st.slider("轉折識別窗口 (Pivots)", 3, 15, 5)
    v_mul = st.slider("量能爆發倍數", 1.0, 3.0, 1.2, 0.1)
    
    st.subheader("🛡️ 風控設定")
    sl_m = st.slider("移動停損 ATR", 1.0, 5.0, 2.0)
    tp_m = st.slider("目標停利 ATR", 3.0, 20.0, 10.0)
    cost_p = st.number_input("單邊成本 (含稅/費/滑價)", value=3.5, step=0.5)

# --- 執行回測 ---
if not df_raw.empty:
    # 建議顯示
    if "趨勢盤" in regime: st.warning("💡 雷達警告：趨勢強勁，建議使用『趨勢線突破』策略並放寬停利。")
    elif "震盪盤" in regime: st.info("💡 雷達提示：盤整蓄勢中，RSI 逆勢操作勝率較高。")

    tester = MomentumBacktester(df_raw)
    params = {'pivot_window': p_win, 'volume_multi': v_mul, 'rsi_period': 14, 'rsi_upper': 70, 'rsi_lower': 30}
    
    metrics, trades = tester.run_strategy(
        strategy_mode, "2024-01-01", "全時段", 
        sl_m, tp_m, params, cost_points=cost_p, timeframe=tf
    )
    
    # 績效顯示
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("勝率", metrics.get("勝率", "0%"))
    c2.metric("淨獲利", metrics.get("淨獲利", "0 TWD"))
    c3.metric("交易次數", metrics.get("交易次數", 0))
    c4.metric("期望值/筆", metrics.get("期望值", "0"))

    # 繪圖
    recent = df_raw.tail(1000)
    fig = go.Figure(data=[go.Candlestick(x=recent['datetime'], open=recent['open'], high=recent['high'], low=recent['low'], close=recent['close'], increasing_line_color='#FF3333', decreasing_line_color='#00CC00')])
    
    if trades:
        rt = [t for t in trades if t['time'] >= recent['datetime'].iloc[0]]
        for t in rt:
            fig.add_annotation(x=t['time'], y=t['price'], text=t['desc'], showarrow=True, arrowhead=1, bgcolor='red' if 'BUY' in t['type'] else 'green', font=dict(color='white'))

    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("📝 歷史成交明細"):
        if trades:
            df_t = pd.DataFrame(trades).rename(columns={'time':'時間','type':'買賣','price':'價格','desc':'動作'})
            st.dataframe(df_t.set_index('時間'), use_container_width=True)
            st.download_button("📥 下載 CSV", df_t.to_csv(index=False, encoding='utf-8-sig'), f"MTX_{strategy_mode}.csv", "text/csv")
else:
    st.warning("請更新資料庫")
