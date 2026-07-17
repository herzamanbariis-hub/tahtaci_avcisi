import json
from signal_engine import generate_signals
from stock_lists import TUM_HISSELER
import config

results = generate_signals(TUM_HISSELER, config.DB_PATH)

# Filter out ENDEKS_KILIDI
results = [r for r in results if r.get('hisse') != 'ENDEKS_KILIDI' and 'error' not in r]

# Sort by tahtaci_score
results.sort(key=lambda x: x.get('tahtaci_score', 0), reverse=True)

top_10 = []
for r in results[:15]:
    trap = r.get('trap_analysis')
    trap_score = trap.trap_score if trap else 0
    smc = r.get('smc_sniper', False)
    
    top_10.append({
        'Hisse': r['hisse'],
        'Skor': r['tahtaci_score'],
        'Durum': r.get('market_status', ''),
        'Ozet': r.get('summary', ''),
        'SMC_Sniper': smc,
        'Tuzak_Skoru': trap_score
    })

with open('top_results.json', 'w', encoding='utf-8') as f:
    json.dump(top_10, f, ensure_ascii=False, indent=2)

print("Top results saved to top_results.json")
