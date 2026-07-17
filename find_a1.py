import json
from analyzer import calculate_tahtaci_score
from stock_lists import TUM_HISSELER

# Sadece sonuclari bulmak icin
found = []
for hisse in TUM_HISSELER:
    try:
        res = calculate_tahtaci_score(hisse)
        corridors = res.get('corridors')
        if corridors is not None and not corridors.empty:
            for idx, row in corridors.iterrows():
                gonderici = str(row['gonderici']).upper()
                alici = str(row['alici']).upper()
                if 'A1' in gonderici or 'A1' in alici:
                    found.append({
                        'hisse': hisse,
                        'gonderici': row['gonderici'],
                        'alici': row['alici'],
                        'ort_transfer': row['ort_transfer'],
                        'korelasyon': row['korelasyon'],
                        'olasilik': row['olasilik']
                    })
    except Exception as e:
        pass

with open('a1_virmans.json', 'w', encoding='utf-8') as f:
    json.dump(found, f, ensure_ascii=False, indent=2)

print("Saved to a1_virmans.json")
