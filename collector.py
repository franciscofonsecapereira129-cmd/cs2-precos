"""Coletor de preços CS2: Skinport + Steam -> data/prices.csv"""
import csv, os, re, sys, time
from datetime import datetime, timezone
import requests

DATA = "data/prices.csv"
ITEMS = "items.txt"
UA = {"User-Agent": "cs2-collector/1.0"}


def load_items():
    with open(ITEMS, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def parse_eur(s):
    s = re.sub(r"[^\d,.]", "", s)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


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


def steam(name):
    r = requests.get(
        "https://steamcommunity.com/market/priceoverview/",
        params={"appid": 730, "currency": 3, "market_hash_name": name},
        headers=UA,
        timeout=30,
    )
    if r.status_code == 429:
        raise RuntimeError("Steam limitou os pedidos (429)")
    if r.status_code != 200:
        return None
    j = r.json()
    if not j.get("success") or not j.get("lowest_price"):
        return None
    vol = int(re.sub(r"\D", "", j.get("volume", "0")) or 0)
    return parse_eur(j["lowest_price"]), vol


def main():
    names = load_items()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []

    try:
        for n, (p, q) in skinport(names).items():
            rows.append([ts, "Skinport", n, p, q])
    except Exception as e:
        print("Aviso Skinport:", e)

    for n in names:
        try:
            res = steam(n)
        except RuntimeError as e:
            print("Aviso Steam:", e)
            break
        except Exception as e:
            print("Aviso Steam", n, e)
            res = None
        if res:
            rows.append([ts, "Steam", n, res[0], res[1]])
        time.sleep(4)

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
