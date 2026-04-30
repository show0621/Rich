# ... 前面代碼保持不變 ...

# 修改模式選擇區
st.subheader("⚙️ 策略參數設定")
col_m1, col_m2 = st.columns(2)

with col_m1:
    mode = st.radio("回測深度", ["壓力測試 (2024至今)", "穩定性測試 (最近3個月)"], horizontal=True)

with col_m2:
    session = st.selectbox("監控時段", ["全時段", "日盤 (08:45-13:45)", "夜盤 (15:00-05:00)"])

start_dt = "2024-01-01" if "壓力測試" in mode else (pd.Timestamp.now() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')

# 執行策略時傳入時段參數
tester = MomentumBacktester(df_raw)
metrics = tester.run_strategy(start_dt, session_type=session)

# ... 後面顯示績效與圖表的代碼保持不變 ...
