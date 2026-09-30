"""Download and build compact India place index from GeoNames cities5000.zip and admin1CodesASCII.txt.
Output: frontend/public/data/places_in.json
"""

import io
import json
import urllib.request
import zipfile
import gzip
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_FILE = ROOT_DIR / "frontend" / "public" / "data" / "places_in.json"

CITIES_URL = "https://download.geonames.org/export/dump/cities5000.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

def build_index():
    print("1. Downloading admin1CodesASCII.txt...")
    req = urllib.request.Request(ADMIN1_URL, headers={"User-Agent": "VajraNowcast/1.1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        admin1_lines = resp.read().decode("utf-8").splitlines()

    admin1_map = {}
    for line in admin1_lines:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("IN."):
            code = parts[0]  # e.g. 'IN.16'
            state_name = parts[1]
            admin1_map[code] = state_name

    print(f"Loaded {len(admin1_map)} Indian administrative subdivisions.")

    print("2. Downloading cities5000.zip...")
    req = urllib.request.Request(CITIES_URL, headers={"User-Agent": "VajraNowcast/1.1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        zip_bytes = io.BytesIO(resp.read())

    with zipfile.ZipFile(zip_bytes) as z:
        with z.open("cities5000.txt") as f:
            cities_lines = io.TextIOWrapper(f, encoding="utf-8").readlines()

    print(f"Processing {len(cities_lines)} worldwide cities...")

    places = []
    for line in cities_lines:
        parts = line.strip().split("\t")
        if len(parts) < 15:
            continue
        country_code = parts[8]
        if country_code != "IN":
            continue

        name = parts[2].strip() if len(parts) > 2 and parts[2].strip() else parts[1].strip()
        lat = round(float(parts[4]), 4)
        lon = round(float(parts[5]), 4)
        admin1_code = f"IN.{parts[10]}"
        state = admin1_map.get(admin1_code, parts[10] or "India")
        pop = int(parts[14]) if parts[14].isdigit() else 0

        # Compact structure: n = name, s = state, lt = lat, ln = lon, p = pop
        places.append({
            "n": name,
            "s": state,
            "lt": lat,
            "ln": lon,
            "p": pop,
        })

    # Sort by population descending
    places.sort(key=lambda x: x["p"], reverse=True)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    json_bytes = json.dumps(places, separators=(",", ":")).encode("utf-8")
    with open(OUTPUT_FILE, "wb") as out:
        out.write(json_bytes)

    gz_bytes = gzip.compress(json_bytes)
    raw_size_kb = len(json_bytes) / 1024
    gz_size_kb = len(gz_bytes) / 1024

    print(f"\nSuccessfully built {len(places)} Indian places in {OUTPUT_FILE}")
    print(f"Raw JSON Size: {raw_size_kb:.1f} KB")
    print(f"Gzipped Size:  {gz_size_kb:.1f} KB (Target < 300 KB: {'PASSED' if gz_size_kb < 300 else 'FAILED'})")

    # Spot checks
    spot_names = ["Karad", "Wardha", "Tezpur", "Satara", "Puri"]
    print("\n--- SPOT CHECKS ---")
    for s in spot_names:
        matched = [p for p in places if p["n"].lower() == s.lower()]
        if matched:
            m = matched[0]
            print(f"• {m['n']} ({m['s']}): Lat={m['lt']}, Lon={m['ln']}, Pop={m['p']:,}")
        else:
            print(f"• {s}: NOT FOUND")

if __name__ == "__main__":
    build_index()
