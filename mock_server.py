from flask import Flask, request, jsonify
import random
from datetime import datetime, timedelta

app = Flask(__name__)

KURUMLAR = [
    "Yatırım Finansman", "Gedik Yatırım", "İş Yatırım", "Garanti BBVA",
    "Yapı Kredi Yatırım", "Ak Yatırım", "Deniz Yatırım", "HSBC Yatırım",
    "Deutsche Bank", "Citi Menkul", "Ünlü Menkul", "BofA Securities",
    "J.P. Morgan", "Goldman Sachs", "Diğer"
]

@app.route("/api/akd", methods=["GET"])
def akd_endpoint():
    hisse = request.args.get("hisse")
    tarih = request.args.get("tarih")
    
    data = []
    for kurum in KURUMLAR:
        data.append({
            "kurum": kurum,
            "net": int(random.gauss(0, 50000)),
            "amount": round(random.uniform(100000, 5000000), 2),
            "price": round(random.uniform(15.0, 50.0), 2)
        })
    return jsonify({"data": data, "success": True, "hisse": hisse, "tarih": tarih})


@app.route("/api/takas", methods=["GET"])
def takas_endpoint():
    hisse = request.args.get("hisse")
    tarih = request.args.get("tarih")
    
    data = []
    for kurum in KURUMLAR:
        data.append({
            "kurum": kurum,
            "oran": round(random.uniform(0.1, 15.0), 2),
            "adet": int(random.uniform(10000, 5000000))
        })
    return jsonify({"data": data, "success": True, "hisse": hisse, "tarih": tarih})


@app.route("/api/price", methods=["GET"])
def price_endpoint():
    hisse = request.args.get("hisse")
    start = request.args.get("start")
    end = request.args.get("end")
    
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
    except:
        return jsonify({"error": "Invalid date format"}), 400
        
    days = (end_date - start_date).days
    
    data = []
    price = 30.0
    for i in range(days + 1):
        curr = start_date + timedelta(days=i)
        if curr.weekday() >= 5:
            continue
            
        change = random.gauss(0, 0.5)
        price += change
        open_p = round(price + random.gauss(0, 0.2), 2)
        high_p = round(max(open_p, price) + abs(random.gauss(0, 0.3)), 2)
        low_p = round(min(open_p, price) - abs(random.gauss(0, 0.3)), 2)
        
        data.append({
            "date": curr.strftime("%Y-%m-%d"),
            "o": open_p,
            "h": high_p,
            "l": low_p,
            "c": round(price, 2),
            "v": int(random.uniform(500000, 5000000))
        })
        
    return jsonify({"data": data, "success": True, "hisse": hisse})


if __name__ == "__main__":
    print("Starting Mock Server on http://localhost:8000")
    app.run(host="127.0.0.1", port=8000, debug=True)
