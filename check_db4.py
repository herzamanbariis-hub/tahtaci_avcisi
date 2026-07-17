import pandas as pd
import sqlite3
import datetime

conn = sqlite3.connect('tahtaci_avcisi.db')

def query_df(sql, params=()):
    return pd.read_sql(sql, conn, params=params)

hisse = "PKART"
akd_df = query_df("SELECT tarih, kurum_adi, net_lot FROM akd_data WHERE hisse = ? ORDER BY tarih", (hisse,))
takas_raw = query_df("SELECT tarih, kurum_adi, saklama_adet FROM takas_data WHERE hisse = ? ORDER BY kurum_adi, tarih", (hisse,))

if not takas_raw.empty:
    takas_raw["delta_saklama"] = takas_raw.groupby("kurum_adi")["saklama_adet"].diff()
    takas_df = takas_raw.dropna(subset=["delta_saklama"]).copy()
else:
    takas_df = pd.DataFrame()

print("AKD DATES:", akd_df['tarih'].unique() if not akd_df.empty else [])
print("TAKAS RAW DATES:", takas_raw['tarih'].unique() if not takas_raw.empty else [])
print("TAKAS DELTA DATES:", takas_df['tarih'].unique() if not takas_df.empty else [])

all_dates = sorted(set(akd_df["tarih"].tolist() + takas_df["tarih"].tolist())) if not takas_df.empty else sorted(set(akd_df["tarih"].tolist()))
print("ALL DATES:", all_dates)

T_PLUS_DAYS = 2
sorted_dates = sorted(set(all_dates))
day_map = {}
for i, d in enumerate(sorted_dates):
    target_idx = i + T_PLUS_DAYS
    if target_idx < len(sorted_dates):
        day_map[d] = sorted_dates[target_idx]
print("DAY MAP:", day_map)

akd_df["tarih_t2"] = akd_df["tarih"].map(day_map)
print("AKD AFTER MAP:\n", akd_df[["tarih", "tarih_t2"]].drop_duplicates())

if not takas_df.empty:
    merged = pd.merge(akd_df.dropna(subset=["tarih_t2"]), takas_df, left_on=["tarih_t2", "kurum_adi"], right_on=["tarih", "kurum_adi"], how="inner")
    print("MERGED COUNT:", len(merged))
