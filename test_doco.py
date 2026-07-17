from signal_engine import calculate_tahtaci_score
import sqlite3, pandas as pd

score = calculate_tahtaci_score('DOCO')
print('Score:', score['tahtaci_score'])
print('Sub-scores:')
for k, v in score['sub_scores'].items():
    print(f'{k}: {v}')

conn = sqlite3.connect('tahtaci_avcisi.db')
df = pd.read_sql("SELECT kurum_adi, net_lot, avg_price FROM akd_data WHERE hisse='DOCO' ORDER BY net_lot DESC LIMIT 5", conn)
print('\nTop Buyers:')
print(df)
df2 = pd.read_sql("SELECT kurum_adi, net_lot, avg_price FROM akd_data WHERE hisse='DOCO' ORDER BY net_lot ASC LIMIT 5", conn)
print('\nTop Sellers:')
print(df2)
