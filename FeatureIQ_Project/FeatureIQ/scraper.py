#!/usr/bin/env python3
"""
FeatureIQ - Apify -> pandas connector

1. Starts apify/cheerio-scraper with the GSMArena page function (or any actor you point it at)
2. Polls the run until it finishes, printing live item counts
3. Downloads the dataset through the Apify API
4. Cleans it (parse mAh / GB / MP / inches / prices, handle missing values, integer dtypes)
5. Writes scraped_smartphones.csv  (+ scraped_smartphones_raw.csv for reproducibility)

Setup:
    pip install apify-client pandas numpy
    export APIFY_TOKEN="apify_api_xxx"        # Console -> Settings -> API & Integrations

Examples:
    # quick smoke test (25 phones, cheap):
    python featureiq_scrape.py --max-results 25

    # full crawl through residential proxies:
    python featureiq_scrape.py --max-results 15000 --proxy residential

    # already have a dataset? skip scraping, just download + clean:
    python featureiq_scrape.py --dataset-id AbCdEf123

    # different actor (e.g. a Store actor for 91mobiles). See its columns first:
    python featureiq_scrape.py --actor bovi/91mobiles-scraper --input-file input_91.json --inspect
"""
import argparse
import inspect
import json
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from apify_client import ApifyClient

# --------------------------------------------------------------------------- config
HERE = Path(__file__).resolve().parent
PAGE_FN_PATH = HERE / "gsmarena_page_function.js"
DEFAULT_ACTOR = "apify/cheerio-scraper"
OUT_CSV = "scraped_smartphones.csv"
RAW_CSV = "scraped_smartphones_raw.csv"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}

# Placeholder FX rates used ONLY to fill the other currency column. UPDATE for your analysis date.
USD_INR = 88.0
EUR_USD = 1.10
GBP_USD = 1.30
BARE_PRICE_CURRENCY = "INR"   # currency assumed when a scraper returns a bare number like 12999

# Analysis choices (tune to your definition of "smartphone")
MIN_RAM_GB = 1          # drops feature phones / pre-smartphone devices
CORE_FIELDS = ["brand", "model_name", "battery_mah", "ram_gb",
               "storage_gb", "primary_camera_mp", "screen_size_in"]
# Rows with a value outside these ranges are treated as parse errors -> missing
SANE = {
    "battery_mah": (500, 20000),
    "ram_gb": (0.25, 32),
    "storage_gb": (0.03, 2048),
    "primary_camera_mp": (0.1, 300),
    "screen_size_in": (1.5, 13),
}


# --------------------------------------------------------------------------- actor input
def gsmarena_input(max_results, proxy, country, concurrency):
    if not PAGE_FN_PATH.exists():
        sys.exit(f"Missing {PAGE_FN_PATH.name} next to this script.")

    if proxy == "residential":
        proxy_cfg = {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]}
        if country:
            proxy_cfg["apifyProxyCountry"] = country
    elif proxy == "datacenter":
        proxy_cfg = {"useApifyProxy": True}  # Apify's default datacenter pool
    else:
        proxy_cfg = {"useApifyProxy": False}

    return {
        "startUrls": [{"url": "https://www.gsmarena.com/makers.php3"}],
        "respectRobotsTxtFile": True,
        # only follow links inside the brand grid, device grid and pager
        "linkSelector": "div.st-text a, div.makers a, div.nav-pages a",
        "pseudoUrls": [
            {"purl": "https://www.gsmarena.com/[\\w+]-phones-[\\d+].php"},
            {"purl": "https://www.gsmarena.com/[\\w+]-phones-f-[\\d+]-[\\d+]-p[\\d+].php"},
            {"purl": "https://www.gsmarena.com/[\\w+]-[\\d+].php"},
        ],
        "keepUrlFragments": False,
        "pageFunction": PAGE_FN_PATH.read_text(encoding="utf-8"),
        "proxyConfiguration": proxy_cfg,
        "proxyRotation": "PER_REQUEST",   # new IP per request spreads load; GSMArena limits per IP
        "maxRequestRetries": 8,
        "maxConcurrency": concurrency,    # keep LOW: the site rate-limits aggressively
        "maxCrawlingDepth": 0,
        "maxPagesPerCrawl": 0,
        "maxResultsPerCrawl": max_results,
        "pageLoadTimeoutSecs": 60,
        "pageFunctionTimeoutSecs": 60,
        "debugLog": False,
    }


# --------------------------------------------------------------------------- Apify API
# apify-client 1.x/2.x return plain dicts and take timeout_secs / wait_secs.
# apify-client 3.x returns typed models and takes timedelta (run_timeout / wait_duration).
# The helpers below work with both.
def _field(obj, snake, camel):
    if isinstance(obj, dict):
        return obj.get(camel)
    return getattr(obj, snake, None)


def run_actor(client, actor_id, run_input, memory_mbytes, timeout_secs):
    actor = client.actor(actor_id)
    if "run_timeout" in inspect.signature(actor.start).parameters:      # v3
        run = actor.start(run_input=run_input, memory_mbytes=memory_mbytes,
                          run_timeout=timedelta(seconds=timeout_secs))
    else:                                                                # v1/v2
        run = actor.start(run_input=run_input, memory_mbytes=memory_mbytes,
                          timeout_secs=timeout_secs)

    run_id = _field(run, "id", "id")
    dataset_id = _field(run, "default_dataset_id", "defaultDatasetId")
    print(f"Run started  : https://console.apify.com/actors/runs/{run_id}")
    print(f"Dataset      : {dataset_id}")

    run_client = client.run(run_id)
    v3 = "wait_duration" in inspect.signature(run_client.wait_for_finish).parameters
    while True:
        info = (run_client.wait_for_finish(wait_duration=timedelta(seconds=60)) if v3
                else run_client.wait_for_finish(wait_secs=60))
        status = _field(info, "status", "status") or "UNKNOWN"
        status = getattr(status, "value", status)
        ds = client.dataset(dataset_id).get()
        n = _field(ds, "item_count", "itemCount") or 0
        print(f"[{time.strftime('%H:%M:%S')}] status={status:<10} items={n}")
        if status in TERMINAL:
            break

    if status != "SUCCEEDED":
        print(f"WARNING: run ended as {status}. Continuing with whatever is in the dataset "
              f"(check the run log in the Console).")
    return dataset_id


def download_items(client, dataset_id):
    print("Downloading dataset ...")
    items = list(client.dataset(dataset_id).iterate_items())
    print(f"Downloaded {len(items)} raw items")
    return items


# --------------------------------------------------------------------------- parsers
def _isna(x):
    return x is None or (isinstance(x, float) and np.isnan(x))


def _f(s):
    return float(s.replace(",", ""))


def parse_battery(x):
    if _isna(x):
        return np.nan
    s = str(x)
    m = re.search(r"(\d[\d,]*)\s*mAh", s, re.I) or re.fullmatch(r"\s*(\d{3,5})\s*", s)
    return _f(m.group(1)) if m else np.nan


def parse_screen(x):
    if _isna(x):
        return np.nan
    s = str(x)
    m = (re.search(r"(\d+(?:\.\d+)?)\s*(?:inches|inch|\"|”|in\b)", s, re.I)
         or re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", s))
    return _f(m.group(1)) if m else np.nan


def parse_camera_mp(x):
    if _isna(x):
        return np.nan
    s = str(x)
    m = re.search(r"(\d+(?:\.\d+)?)\s*MP", s, re.I) or re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*", s)
    return _f(m.group(1)) if m else np.nan


_RAM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB|MB)\s*RAM", re.I)
_STO_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB|MB)", re.I)


def _to_gb(v, unit):
    return {"TB": v * 1024, "GB": v, "MB": v / 1024}[unit.upper()]


def _base_variant(x):
    """'128GB 8GB RAM, 256GB 8GB RAM' -> ('128GB 8GB RAM'). Base config = first listed variant."""
    return str(x).split(",")[0]


def parse_ram(x):
    if _isna(x):
        return np.nan
    m = _RAM_RE.search(_base_variant(x))
    return _to_gb(_f(m.group(1)), m.group(2)) if m else np.nan


def parse_storage(x):
    if _isna(x):
        return np.nan
    v = _RAM_RE.sub(" ", _base_variant(x))      # remove RAM tokens so '4GB RAM' isn't read as storage
    m = _STO_RE.search(v)
    return _to_gb(_f(m.group(1)), m.group(2)) if m else np.nan


_NUM = r"([\d,]+(?:\.\d+)?)"
_PRICE_PATTERNS = {
    "INR": [r"₹\s*" + _NUM, _NUM + r"\s*INR", r"INR\s*" + _NUM, r"Rs\.?\s*" + _NUM],
    "USD": [r"\$\s*" + _NUM, _NUM + r"\s*USD"],
    "EUR": [r"€\s*" + _NUM, _NUM + r"\s*EUR"],
    "GBP": [r"£\s*" + _NUM, _NUM + r"\s*GBP"],
}


def parse_prices(x):
    """'$ 799.99 / € 899.00 / ₹ 79,999' -> {'USD': 799.99, 'EUR': 899.0, 'INR': 79999.0}"""
    out = {}
    if _isna(x):
        return out
    s = str(x)
    for cur, pats in _PRICE_PATTERNS.items():
        for p in pats:
            m = re.search(p, s, re.I)
            if m:
                try:
                    out[cur] = _f(m.group(1))
                    break
                except ValueError:
                    pass
    if not out:
        m = re.fullmatch(r"\s*([\d,]+(?:\.\d+)?)\s*", s)
        if m:
            out[BARE_PRICE_CURRENCY] = _f(m.group(1))
    return out


def price_to_usd_inr(p):
    if not p:
        return (np.nan, np.nan, None)
    usd = p.get("USD")
    if usd is None and "EUR" in p:
        usd = p["EUR"] * EUR_USD
    if usd is None and "GBP" in p:
        usd = p["GBP"] * GBP_USD
    if usd is None and "INR" in p:
        usd = p["INR"] / USD_INR
    inr = p.get("INR", usd * USD_INR if usd is not None else np.nan)
    src = next((c for c in ("INR", "USD", "EUR", "GBP") if c in p), None)
    return (usd if usd is not None else np.nan, inr, src)


# --------------------------------------------------------------------------- cleaning
def norm_col(c):
    return re.sub(r"[^a-z0-9]+", "_", str(c).lower()).strip("_")


# Candidate column names per target field (first match wins, later ones fill gaps).
# Custom page function -> the *_raw / *_hl names. Store actors -> the generic names.
ALIASES = {
    "brand": ["brand", "manufacturer", "make"],
    "model_name": ["model_name", "model", "name", "device_name", "title"],
    "price": ["price_raw", "price", "best_buy_price", "price_inr", "price_usd"],
    "battery": ["battery_hl", "battery_raw", "battery", "battery_capacity", "battery_mah"],
    "memory": ["memory_raw", "memory", "internal_memory", "ram_storage"],
    "ram": ["ram", "ram_gb"],
    "storage": ["storage", "storage_gb", "internal_storage", "rom"],
    "camera": ["main_camera_raw", "camera_hl", "primary_camera", "main_camera", "camera", "rear_camera"],
    "screen": ["display_size_raw", "display_size_hl", "screen_size", "display_size", "display", "screen"],
    "url": ["url", "device_url", "link"],
}


def _series(df, key):
    """First existing candidate column as a Series (or all-NaN)."""
    for c in ALIASES[key]:
        if c in df.columns:
            return df[c]
    return pd.Series(np.nan, index=df.index, dtype="object")


def _coalesce(df, key, parser):
    out = pd.Series(np.nan, index=df.index, dtype="float64")
    for c in ALIASES[key]:
        if c in df.columns:
            out = out.fillna(df[c].map(parser).astype("float64"))
    return out


def clean(items):
    raw = pd.json_normalize(items)
    raw.columns = [norm_col(c) for c in raw.columns]
    df = pd.DataFrame(index=raw.index)

    df["brand"] = _series(raw, "brand").astype("string").str.strip()
    df["model_name"] = _series(raw, "model_name").astype("string").str.strip()

    # --- prices (multi-currency text -> USD + INR) ---
    price_txt = pd.Series(np.nan, index=raw.index, dtype="object")
    for c in ALIASES["price"]:
        if c in raw.columns:
            price_txt = price_txt.where(price_txt.notna(), raw[c])
    conv = price_txt.map(parse_prices).map(price_to_usd_inr)
    df["price_usd"] = conv.map(lambda t: t[0])
    df["price_inr"] = conv.map(lambda t: t[1])
    df["price_original_currency"] = conv.map(lambda t: t[2])

    # --- specs ---
    df["battery_mah"] = _coalesce(raw, "battery", parse_battery)
    df["screen_size_in"] = _coalesce(raw, "screen", parse_screen)
    df["primary_camera_mp"] = _coalesce(raw, "camera", parse_camera_mp)

    ram = _coalesce(raw, "memory", parse_ram)
    sto = _coalesce(raw, "memory", parse_storage)
    df["ram_gb"] = ram.fillna(_coalesce(raw, "ram", _plain_gb))
    df["storage_gb"] = sto.fillna(_coalesce(raw, "storage", _plain_gb))

    # --- extras (kept if the scraper provided them) ---
    for src, dst in [("announced", "announced"), ("status", "status"), ("os", "os"),
                     ("chipset", "chipset"), ("network_tech", "network_tech"), ("url", "url")]:
        if src in raw.columns:
            df[dst] = raw[src]
    for src, dst in [("popularity_raw", "popularity_hits"), ("fans_raw", "fans")]:
        if src in raw.columns:
            nums = raw[src].astype("string").str.extractall(r"([\d,]{3,})")[0]
            df[dst] = pd.to_numeric(nums.groupby(level=0).last().str.replace(",", ""), errors="coerce")
    if "announced" in df.columns:
        df["release_year"] = pd.to_numeric(df["announced"].astype("string").str.extract(r"(\d{4})")[0],
                                           errors="coerce")

    # --- sanity ranges -> NaN ---
    for col, (lo, hi) in SANE.items():
        df.loc[~df[col].between(lo, hi), col] = np.nan

    n_raw = len(df)
    missing_report = df[CORE_FIELDS].isna().sum().sort_values(ascending=False)

    # --- drop rows without core specs; keep rows without price (flagged) ---
    df = df.dropna(subset=CORE_FIELDS)
    df = df[df["brand"].str.len() > 0]
    df = df[df["ram_gb"] >= MIN_RAM_GB]

    dedupe_key = "url" if "url" in df.columns else ["brand", "model_name"]
    df = df.drop_duplicates(subset=dedupe_key).copy()

    df["has_price"] = df["price_usd"].notna()

    # --- integer formatting (nullable Int64 so missing prices stay <NA>) ---
    for col in ["battery_mah", "ram_gb", "storage_gb", "price_inr", "price_usd"]:
        df[col] = df[col].round().astype("Int64")
    df["primary_camera_mp"] = df["primary_camera_mp"].round(1)
    df["screen_size_in"] = df["screen_size_in"].round(2)
    for col in ["release_year", "popularity_hits", "fans"]:
        if col in df.columns:
            df[col] = df[col].round().astype("Int64")

    lead = ["brand", "model_name", "price_inr", "price_usd", "battery_mah", "ram_gb",
            "storage_gb", "primary_camera_mp", "screen_size_in"]
    df = df[lead + [c for c in df.columns if c not in lead]].reset_index(drop=True)

    print("\n=== Cleaning report ===")
    print(f"raw rows                : {n_raw}")
    print(f"clean rows kept         : {len(df)}")
    print("missing/unparseable core fields in raw data:")
    print(missing_report.to_string())
    print(f"rows with a price       : {int(df['has_price'].sum())} "
          f"({df['has_price'].mean():.0%})" if len(df) else "")
    return df


def _plain_gb(x):
    """Fallback for actors that return RAM/storage as '8', '8 GB', '1 TB' without the word RAM."""
    if _isna(x):
        return np.nan
    m = re.search(r"(\d+(?:\.\d+)?)\s*(TB|GB|MB)?", str(x), re.I)
    if not m:
        return np.nan
    return _to_gb(_f(m.group(1)), m.group(2) or "GB")


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="FeatureIQ Apify -> pandas connector")
    ap.add_argument("--token", default=os.getenv("APIFY_TOKEN"))
    ap.add_argument("--actor", default=DEFAULT_ACTOR)
    ap.add_argument("--input-file", help="JSON run input for a non-default actor")
    ap.add_argument("--dataset-id", help="Skip scraping; download + clean this dataset")
    ap.add_argument("--max-results", type=int, default=15000)
    ap.add_argument("--proxy", choices=["residential", "datacenter", "none"], default="residential")
    ap.add_argument("--proxy-country", default=None, help="e.g. US, IN (optional)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--memory", type=int, default=2048, help="Actor memory in MB")
    ap.add_argument("--timeout-hours", type=float, default=6.0)
    ap.add_argument("--inspect", action="store_true", help="Print raw columns/sample and exit")
    ap.add_argument("--out", default=OUT_CSV)
    args = ap.parse_args()

    if not args.token:
        sys.exit("Set APIFY_TOKEN (or pass --token).")
    client = ApifyClient(args.token)

    if args.dataset_id:
        dataset_id = args.dataset_id
    else:
        if args.input_file:
            run_input = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
        elif args.actor == DEFAULT_ACTOR:
            run_input = gsmarena_input(args.max_results, args.proxy, args.proxy_country, args.concurrency)
        else:
            sys.exit("For a non-default actor, pass --input-file with its run input JSON.")
        dataset_id = run_actor(client, args.actor, run_input, args.memory,
                               int(args.timeout_hours * 3600))

    items = download_items(client, dataset_id)
    if not items:
        sys.exit("Dataset is empty - open the run log in the Apify Console (likely blocked / wrong selectors).")

    raw_df = pd.json_normalize(items)
    raw_df.to_csv(RAW_CSV, index=False)
    print(f"Saved raw data -> {RAW_CSV}")

    if args.inspect:
        print("\nColumns:", list(raw_df.columns))
        print(raw_df.head(5).T.to_string())
        return

    df = clean(items)
    df.to_csv(args.out, index=False)
    print(f"\nSaved {len(df)} rows -> {args.out}")
    if len(df) < 10000:
        print("NOTE: fewer than 10,000 clean rows. Options: relax CORE_FIELDS/MIN_RAM_GB, "
              "or add a second source (e.g. 91mobiles) and concat the CSVs.")
    print(df.head(10).to_string())


if __name__ == "__main__":
    main()
