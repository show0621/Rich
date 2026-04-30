import pandas as pd
import sqlite3
import requests
import zipfile
import io
import time
from datetime import datetime, timedelta

class MTXDatabase:
    def __init__(self, db_name="mtx_data.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)

    def fetch_single_day(self, date_str):
        """從期交所下載單日逐筆資料並轉為 1 分 K"""
        url = f"https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV/Daily_{date_str}.zip"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 404 or not response.content.startswith(b'PK'):
                return pd.DataFrame() # 找不到檔案或非 ZIP 檔
            
            z = zipfile.ZipFile(io.BytesIO(response.content))
            csv_filename = z.namelist()[0]
            df = pd.read_csv(z.open(csv_filename), encoding='cp950', dtype=str)
            df.columns = [c.strip() for c in df.columns]
            
            df_mtx = df[df['商品代號'].str.strip() == 'MTX'].copy()
            if df_mtx.empty: return pd.DataFrame()

            # 自動換倉邏輯：找成交量最大的月份
            df_mtx['成交數量(B+S)'] = df_mtx['成交數量(B+S)'].astype(int)
            front_month = df_mtx.groupby('到期月份(週別)')['成交數量(B+S)'].sum().idxmax()
            df_front = df_mtx[df_mtx['到期月份(週別)'] == front_month].copy()
            
            # 轉換時間與價格
            df_front['datetime'] = pd.to_datetime(df_front['成交日期'] + ' ' + df_front['成交時間'], format='%Y%m%d %H%M%S')
            df_front['price'] = df_front['成交價格'].astype(float)
            
            # Resample 成 1分 K
            df_front.set_index('datetime', inplace=True)
            df_1m = df_front.resample('1min').agg({'price': 'ohlc', '成交數量(B+S)': 'sum'}).dropna()
            df_1m.columns = ['open', 'high', 'low', 'close', 'volume']
            df_1m.reset_index(inplace=True)
            return df_1m
        except Exception as e:
            print(f"抓取 {date_str} 失敗: {e}")
            return pd.DataFrame()

    def update_data(self, target_days=3):
        """抓取最近 N 個有效交易日寫入資料庫"""
        today = datetime.today()
        all_data = []
        days_collected = 0
        days_lookback = 0
        
        while days_collected < target_days and days_lookback < 15:
            days_lookback += 1
            target_date = today - timedelta(days=days_lookback)
            
            if target_date.weekday() >= 5: continue # 跳過週末
                
            date_str = target_date.strftime("%Y_%m_%d")
            df = self.fetch_single_day(date_str)
            
            if not df.empty:
                all_data.append(df)
                days_collected += 1
            
            time.sleep(1) # 禮貌性延遲
            
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            final_df.sort_values('datetime', inplace=True)
            final_df.to_sql("kline_1m", self.conn, if_exists="replace", index=False)
            return True
        return False

    def load_data(self):
        try:
            return pd.read_sql("SELECT * FROM kline_1m ORDER BY datetime ASC", self.conn, parse_dates=['datetime'])
        except:
            return pd.DataFrame()
