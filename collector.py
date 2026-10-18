"""Coletor de preços CS2 (Steam + Skinport + CSFloat opcional) -> data/prices.csv"""
import csv, os, re, sys, time
from datetime import datetime, timezone
import requests

DATA = "data/prices.csv"
ITEMS = "items.txt"
AUTO = "data/auto_items.txt"
UA = {"User-Agent": "cs2-collector/1.0"}

# Escolha automática de itens baratos (só acontece uma vez; depois a lista fica guardada)
MIN_PRICE = 0.20   # € mínimo
MAX_PRICE = 3.00   # € máximo
MIN_QTY = 300      # mínimo de unidades à venda (liquidez)
N_AUTO = 30        # quantos itens escolher


def load_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def skinport_all():
    r = requests.get(
        "https://api.skinport.com/v1/items",
        params={"app_id": 730, "currency": "EUR"},
        headers={**UA, "Accept-Encoding": "br"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def pick_auto(todos, manual):
    guardados = load_lines(AUTO)
    if guardados:
        return guardados
    cand = []
    for it in todos:
        p = it.get("min_price")
        q = it.get("quantity") or 0
        n = it.get("market_hash_name")
        if p is not None and MIN_PRICE <= p <= MAX_PRICE and q >= MIN_QTY and n not in manual:
            cand.append((q, n))
    cand.sort(reverse=True)
    nomes = [n for _, n in cand[:N_AUTO]]
    if nomes:
        os.makedirs("data", exist_ok=True)
        with open(AUTO, "w", encoding="utf-8") as f:
            f.write("\n".join(nomes) + "\n")
    return nomes


def parse_eur(t):
    t = re.sub(r"[^\d,.]", "", t)
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def steam(name):
    r = requests.get(
        "https://steamcommunity.com/market/priceoverview/",
        params={"appid": 730, "currency": 3, "market_hash_name": name},
        headers=UA,
        timeout=30,
    )
    if r.status_code == 429:
        raise RuntimeError("Steam limitou os pedidos (429)")
    r.raise_for_status()
    j = r.json()
    if not j.get("success") or not j.get("lowest_price"):
        return None
    vol = int(re.sub(r"\D", "", j.get("volume", "0")) or 0)
    return parse_eur(j["lowest_price"]), vol


def usd_to_eur():
    r = requests.get(
        "https://api.frankfurter.dev/v1/latest",
        params={"base": "USD", "symbols": "EUR"},
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    return float(r.json()["rates"]["EUR"])


def csfloat(name, key):
    r = requests.get(
        "https://csfloat.com/api/v1/listings",
        params={"market_hash_name": name, "sort_by": "lowest_price", "limit": 50},
        headers={**UA, "Authorization": key},
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    lista = j.get("data", []) if isinstance(j, dict) else j
    precos = []
    for l in lista:
        if l.get("type") == "auction":
            continue
        if (l.get("item") or {}).get("market_hash_name") != name:
            continue
        if l.get("price"):
            precos.append(l["price"] / 100)
    if not precos:
        return None
    return min(precos), len(precos)


def main():
    manual = load_lines(ITEMS)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    auto = []

    try:
        todos = skinport_all()
        auto = pick_auto(todos, set(manual))
        wanted = set(manual) | set(auto)
        for it in todos:
            n = it.get("market_hash_name")
            if n in wanted and it.get("min_price") is not None:
                rows.append([ts, "Skinport", n, round(float(it["min_price"]), 2), it.get("quantity") or 0])
    except Exception as e:
        print("Aviso Skinport:", e)

    # Steam: um pedido por item, com pausa para não ser bloqueado
    erros_steam = 0
    for n in manual + [x for x in auto if x not in manual]:
        try:
            res = steam(n)
        except RuntimeError as e:
            print("Aviso Steam:", e, "- a parar a Steam nesta corrida")
            break
        except Exception as e:
            erros_steam += 1
            print("Aviso Steam", n, e)
            res = None
            if erros_steam >= 3:
                print("Aviso Steam: demasiados erros, a parar")
                break
        if res:
            rows.append([ts, "Steam", n, round(res[0], 2), res[1]])
        time.sleep(3.5)

    key = os.environ.get("CSFLOAT_API_KEY", "").strip()
    if key:
        try:
            taxa = usd_to_eur()
            for n in manual:
                try:
                    res = csfloat(n, key)
                except Exception as e:
                    print("Aviso CSFloat", n, e)
                    res = None
                if res:
                    rows.append([ts, "CSFloat", n, round(res[0] * taxa, 2), res[1]])
                time.sleep(2)
        except Exception as e:
            print("Aviso CSFloat/câmbio:", e)

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
