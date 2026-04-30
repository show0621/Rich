from database import MTXDatabase
import datetime

print(f"啟動自動更新排程：{datetime.datetime.now()}")
db = MTXDatabase()

# 目標設定為 1，因為每天跑一次，只需要抓最新 1 天即可
if db.update_data(target_days=1):
    print("✅ 資料庫疊加更新成功！")
else:
    print("⚠️ 沒有新資料或更新失敗。")
