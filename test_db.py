import sqlite3, pandas as pd
conn = sqlite3.connect('tahtaci_avcisi.db')
df = pd.read_sql("SELECT tarih, count(*) FROM takas_data WHERE hisse='EREGL' GROUP BY tarih", conn)
print(df)
