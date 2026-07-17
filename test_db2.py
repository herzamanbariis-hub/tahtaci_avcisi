import sqlite3, pandas as pd
conn = sqlite3.connect('tahtaci_avcisi.db')
df = pd.read_sql("SELECT kurum_adi, net_lot, avg_price FROM akd_data WHERE hisse='AKBNK' ORDER BY net_lot DESC LIMIT 5", conn)
print("Top Buyers:")
print(df)
df2 = pd.read_sql("SELECT kurum_adi, net_lot, avg_price FROM akd_data WHERE hisse='AKBNK' ORDER BY net_lot ASC LIMIT 5", conn)
print("\nTop Sellers:")
print(df2)
