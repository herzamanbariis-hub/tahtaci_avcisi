import pandas as pd
import sqlite3

conn = sqlite3.connect('tahtaci_avcisi.db')
print("AKD:")
print(pd.read_sql('SELECT tarih, COUNT(*) FROM akd_data WHERE hisse="PKART" GROUP BY tarih', conn))
print("\nTAKAS:")
print(pd.read_sql('SELECT tarih, COUNT(*) FROM takas_data WHERE hisse="PKART" GROUP BY tarih', conn))
