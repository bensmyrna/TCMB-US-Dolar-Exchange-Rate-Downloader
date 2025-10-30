#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, subprocess, importlib, datetime as dt, time, xml.etree.ElementTree as ET
from typing import Optional, Dict

# --- Eksik paketleri bu Python'a (sys.executable) kur ---
def ensure(pkg):
    try:
        importlib.import_module(pkg)
    except ImportError:
        print(f"{pkg} kuruluyor...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])
    finally:
        globals()[pkg] = importlib.import_module(pkg)

for p in ["requests", "pandas", "openpyxl", "certifi", "urllib3"]:
    ensure(p)

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import certifi

# --- Ayarlar ---
BASE_URL = "https://www.tcmb.gov.tr/kurlar/{ym}/{dmy}.xml"
TR_DAYNAMES = {0:"Pazartesi",1:"Salı",2:"Çarşamba",3:"Perşembe",4:"Cuma",5:"Cumartesi",6:"Pazar"}
SLEEP_BETWEEN = 0.05      # istekler arası minik bekleme
CONNECT_TIMEOUT = 5       # saniye
READ_TIMEOUT = 15         # saniye

# --- Requests Session: retry + backoff ---
session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (TCMB-Downloader)"})
retry = Retry(
    total=5, connect=5, read=5,
    backoff_factor=0.6,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
session.mount("https://", adapter)
session.mount("http://", adapter)

def fetch_xml_for_date(date: dt.date) -> Optional[str]:
    ym, dmy = date.strftime("%Y%m"), date.strftime("%d%m%Y")
    url = BASE_URL.format(ym=ym, dmy=dmy)
    try:
        r = session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), verify=certifi.where())
        if r.status_code == 200 and r.text.strip():
            return r.text
        return None  # 404 vb. gün yoksa
    except requests.RequestException:
        return None

def parse_usd(xml_text: str) -> Optional[Dict[str, float]]:
    try:
        root = ET.fromstring(xml_text)
        for c in root.findall("Currency"):
            if c.attrib.get("CurrencyCode") == "USD":
                def val(tag):
                    n = c.find(tag)
                    if n is None or not n.text: return None
                    t = n.text.strip().replace(",", ".")
                    try: return float(t)
                    except: return None
                return {"buy": val("ForexBuying"), "sell": val("ForexSelling")}
    except ET.ParseError:
        return None

def main():
    # Örnek test için: 2020-12-01 … 2020-12-31
    try:
        start_in = input("Başlangıç tarihi (YYYY-AA-GG): ").strip()
        end_in   = input("Bitiş tarihi (YYYY-AA-GG): ").strip()
        start, end = dt.date.fromisoformat(start_in), dt.date.fromisoformat(end_in)
    except Exception:
        print("Tarih biçimi hatalı. Örnek: 2020-12-01")
        return

    rows, missing = [], []
    total = found = 0
    d = start
    print("\nİndirilmeye başlandı...\n")

    try:
        while d <= end:
            total += 1
            dayname = TR_DAYNAMES[d.weekday()]
            xml = fetch_xml_for_date(d)
            if xml:
                usd = parse_usd(xml)
                if usd and (usd["buy"] is not None or usd["sell"] is not None):
                    rows.append({
                        "tarih": d.strftime("%d.%m.%Y"),
                        "haftanin_gunu": dayname,
                        "usd_alis": usd["buy"],
                        "usd_satis": usd["sell"],
                    })
                    found += 1
                    print(f"✓ {d.isoformat()} ({dayname}): veri bulundu ({usd['buy']} / {usd['sell']})")
                else:
                    missing.append(f"{d.strftime('%d.%m.%Y')},{dayname}")
                    print(f"– {d.isoformat()} ({dayname}): XML var ama USD alanları boş")
            else:
                missing.append(f"{d.strftime('%d.%m.%Y')},{dayname}")
                print(f"– {d.isoformat()} ({dayname}): dosya yok (hafta sonu/tatil) veya bağlanılamadı")

            d += dt.timedelta(days=1)
            time.sleep(SLEEP_BETWEEN)
    except KeyboardInterrupt:
        print("\nDurduruldu (Ctrl+C). O ana dek toplanan veriler kaydediliyor...\n")

    if not rows:
        print("Toplanacak veri bulunamadı.")
        return

    df = pandas.DataFrame(rows)
    out_xlsx = f"tcmb_usd_{start}_{end}.xlsx".replace(":", "-")
    df.to_excel(out_xlsx, index=False)

    if missing:
        with open("eksik_gunler.txt","w",encoding="utf-8") as f:
            f.write("tarih,haftanin_gunu\n" + "\n".join(missing))
        print(f"Eksik günler yazıldı: eksik_gunler.txt ({len(missing)} satır)")

    print(f"\nÖzet: {found}/{total} gün bulundu. Kaydedildi: {out_xlsx}")

if __name__ == "__main__":
    main()
