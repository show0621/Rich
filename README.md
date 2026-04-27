# 微台指動能當沖監控專案 (MTX-Momentum)

## 策略邏輯
- **Trend Filter (30m):** 價格高於 EMA20 視為多頭。
- **Momentum Entry (5m):** RSI 交叉 50 作為進場訊號。
- **Cost:** 每筆交易扣除 2 點滑價與稅費。

## 交易日誌與錯誤修正
- [2026-04-27] 初始化專案，整合 FinMind 與 SQLite。
- [待紀錄] 觀察千點震盪下的 MDD 表現。
