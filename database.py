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
                return pd.DataFrame() 
            
            z = zipfile.ZipFile(io.BytesIO(response.content))
            csv_filename = z.namelist()[0]
            df = pd.read_csv(z.open(csv_filename), encoding='cp950', dtype=str)
            df.columns = [c.strip() for c in df.columns]
            
            df_mtx = df[df['商品代號'].str.strip() == 'MTX'].copy()
            if df_mtx.empty: return pd.DataFrame()

            df_mtx['成交數量(B+S)'] = df_mtx['成交數量(B+S)'].astype(int)
            front_month = df_mtx.groupby('到期月份(週別)')['成交數量(B+S)'].sum().idxmax()
            df_front = df_mtx[df_mtx['到期月份(週別)'] == front_month].copy()
            
            df_front['datetime'] = pd.to_datetime(df_front['成交日期'] + ' ' + df_front['成交時間'], format='%Y%m%d %H%M%S')
            df_front['price'] = df_front['成交價格'].astype(float)
            
            df_front.set_index('datetime', inplace=True)
            df_1m = df_front.resample('1min').agg({'price': 'ohlc', '成交數量(B+S)': 'sum'}).dropna()
            df_1m.columns = ['open', 'high', 'low', 'close', 'volume']
            df_1m.reset_index(inplace=True)
            return df_1m
        except Exception as e:
            print(f"抓取 {date_str} 失敗: {e}")
            return pd.DataFrame()

    def update_data(self, target_days=3):
        """抓取最新資料，並與舊資料庫完美融合累積"""
        today = datetime.today()
        new_data_list = []
        days_collected = 0
        days_lookback = 0
        
        # 1. 抓取新資料
        while days_collected < target_days and days_lookback < 15:
            days_lookback += 1
            target_date = today - timedelta(days=days_lookback)
            if target_date.weekday() >= 5: continue
                
            date_str = target_date.strftime("%Y_%m_%d")
            df = self.fetch_single_day(date_str)
            
            if not df.empty:
                new_data_list.append(df)
                days_collected += 1
            time.sleep(1)
            
        if not new_data_list:
            return False

        new_df = pd.concat(new_data_list, ignore_index=True)

        # 2. 讀取舊資料庫進行合併與去重 (累積引擎的核心)
        existing_df = self.load_data()
        if not existing_df.empty:
            final_df = pd.concat([existing_df, new_df], ignore_index=True)
            # 依據時間去重，保留最新的資料
            final_df.drop_duplicates(subset=['datetime'], keep='last', inplace=True)
        else:
            final_df = new_df

        # 3. 排序後存回資料庫
        final_df.sort_values('datetime', inplace=True)
        final_df.to_sql("kline_1m", self.conn, if_exists="replace", index=False)
        return True

    def load_data(self):
        try:
            return pd.read_sql("SELECT * FROM kline_1m ORDER BY datetime ASC", self.conn, parse_dates=['datetime'])
        except:
            return pd.DataFrame()
