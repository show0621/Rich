import pandas as pd
import sqlite3
from FinMind.data import DataLoader

class MTXDatabase:
    def __init__(self, db_name="mtx_data.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.dl = DataLoader()

    def update_data(self, start_date="2024-01-01"):
        """獲取微台(MTX)資料並寫入 SQLite"""
        try:
            df = self.dl.taiwan_futures_daily(
                futures_id="MTX",
                start_date=start_date
            )
            if not df.empty:
                df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'])
                # 使用 replace 確保資料是最新的
                df.to_sql("kline_1m", self.conn, if_exists="replace", index=False)
                return True
        except Exception as e:
            print(f"Error updating: {e}")
        return False

    def load_data(self):
        return pd.read_sql("SELECT * FROM kline_1m ORDER BY datetime ASC", self.conn, parse_dates=['datetime'])
