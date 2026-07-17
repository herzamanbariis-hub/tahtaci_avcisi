import sqlite3
import pandas as pd

conn = sqlite3.connect('tahtaci_avcisi.db')
df = pd.read_sql("SELECT * FROM price_data WHERE tarih='2026-07-09'", conn)
print(df)
