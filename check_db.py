import sqlite3
conn = sqlite3.connect('tahtaci_avcisi.db')
c = conn.cursor()
c.execute("SELECT COUNT(*), MAX(tarih) FROM akd_data WHERE hisse='YKBNK'")
print('AKD:', c.fetchall())
c.execute("SELECT COUNT(*), MAX(tarih) FROM takas_data WHERE hisse='YKBNK'")
print('TAKAS:', c.fetchall())
