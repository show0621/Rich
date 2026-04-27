import pandas as pd
import sqlite3
from FinMind.data import DataLoader

class MTXDatabase:
    def __init__(self, db_name="mtx_data.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.dl = DataLoader()

    def update_data(self, start_date="2024-01-01"):
        """抓取 FinMind 資料並更新至資料庫"""
        # 注意：此處以 MTX (微台) 為例，若無資料可換成 TX (大台) 測試邏輯
        df = self.dl.taiwan_futures_daily(
            futures_id="MTX",
            start_date=start_date
        )
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'])
            df.to_sql("kline_1m", self.conn, if_exists="replace", index=False)
            return True
        return False

    def load_data(self):
        return pd.read_sql("SELECT * FROM kline_1m", self.conn, parse_dates=['datetime'])
