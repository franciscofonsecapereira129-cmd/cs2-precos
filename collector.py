"""Coletor de preços CS2: Skinport + DMarket -> data/prices.csv"""
import csv, os, sys, time
from datetime import datetime, timezone
import requests

DATA = "data/prices.csv"
ITEMS = "items.txt"
UA = {"User-Agent": "cs2-collector/1.0"}


def load_items():
    with open(ITEMS, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def skinport(names):
    r = requests.get(
        "https://api.skinport.com/v1/items",
        params={"app_id": 730, "currency": "EUR"},
        headers={**UA, "Accept-Encoding": "br"},
        timeout=60,
    )
    r.raise_for_status()
    wanted, out = set(names), {}
    for it in r.json():
        n = it.get("market_hash_name")
        if n in wanted and it.get("min_price") is not None:
            out[n] = (float(it["min_price"]), it.get("quantity") or 0)
    return out


def usd_to_eur():
    r = requests.get(
        "https://api.frankfurter.dev/v1/latest",
        params={"base": "USD", "symbols": "EUR"},
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    return float(r.json()["rates"]["EUR"])


def dmarket(name):
    r = requests.get(
        "https://api.dmarket.com/exchange/v1/market/items",
        params={
            "gameId": "a8db",
            "title": name,
            "currency": "USD",
            "limit": 50,
            "orderBy": "price",
            "orderDir": "asc",
        },
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    precos = []
    for o in r.json().get("objects", []):
        if o.get("title") != name:
            continue
        usd = (o.get("price") or {}).get("USD")
        if usd:
            precos.append(int(usd) / 100)
    if not precos:
        return None
    return min(precos), len(precos)


def main():
    names = load_items()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []

    try:
        for n, (p, q) in skinport(names).items():
            rows.append([ts, "Skinport", n, round(p, 2), q])
    except Exception as e:
        print("Aviso Skinport:", e)

    try:
        taxa = usd_to_eur()
        for n in names:
            try:
                res = dmarket(n)
            except Exception as e:
                print("Aviso DMarket", n, e)
                res = None
            if res:
                rows.append([ts, "DMarket", n, round(res[0] * taxa, 2), res[1]])
            time.sleep(1)
    except Exception as e:
        print("Aviso DMarket/câmbio:", e)

    if not rows:
        print("Sem dados nesta corrida.")
        sys.exit(1)

    os.makedirs("data", exist_ok=True)
    novo = not os.path.exists(DATA)
    with open(DATA, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["ts", "market", "item", "price_eur", "qty"])
        w.writerows(rows)
    print(f"{len(rows)} preços guardados.")


if __name__ == "__main__":
    main()
