"""Collect SEC EDGAR filing metadata for a small ticker watchlist.

Requires SEC_USER_AGENT set to a descriptive application/contact string.
Does not bypass SEC access restrictions. Existing output is preserved on failure.
"""
import gzip
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
WATCHLIST = BASE / "data" / "sec_watchlist.txt"
OUTPUT = BASE / "data" / "sec_filings.json"

USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip()
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Encoding": "identity",
}
TARGET_FORMS = {
    "S-1", "S-3", "F-1", "F-3", "424B1", "424B2", "424B3", "424B4", "424B5",
    "8-K", "6-K", "10-K", "10-Q", "SC 13D", "SC 13G", "13D", "13G",
    "DEF 14A", "PRE 14A", "EFFECT", "4", "3", "5",
}


def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                body = gzip.decompress(body)
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"SEC HTTP ERROR: {exc.code}", flush=True)
        print(f"REQUEST URL: {url}", flush=True)
        print(f"RETRY AFTER: {exc.headers.get('Retry-After', 'not provided')}", flush=True)
        raise
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"SEC REQUEST ERROR: {url}: {exc}", flush=True)
        raise


def main():
    if not USER_AGENT or "\n" in USER_AGENT or "\r" in USER_AGENT:
        raise RuntimeError("Set SEC_USER_AGENT GitHub Actions secret to a single-line app name and contact email")
    if not WATCHLIST.exists():
        raise FileNotFoundError(f"Watchlist not found: {WATCHLIST}")

    tickers = list(dict.fromkeys(
        line.strip().upper() for line in WATCHLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ))[:100]
    if not tickers:
        raise RuntimeError("Watchlist is empty; preserving previous SEC output")
    print("Watchlist:", len(tickers), flush=True)

    # If this initial request fails, the previous output is never touched.
    mapping = get_json("https://www.sec.gov/files/company_tickers.json")
    ticker_to_cik = {
        item["ticker"].upper(): str(item["cik_str"]).zfill(10)
        for item in mapping.values()
    }

    results, errors = [], []
    successful_tickers = 0
    for ticker in tickers:
        cik = ticker_to_cik.get(ticker)
        if not cik:
            errors.append({"ticker": ticker, "error": "SEC CIK not found"})
            continue
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        try:
            company = get_json(url)
            recent = company.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            documents = recent.get("primaryDocument", [])
            for form, date, accession, document in zip(forms, dates, accessions, documents):
                if form not in TARGET_FORMS:
                    continue
                accession_no_dash = accession.replace("-", "")
                results.append({
                    "ticker": ticker,
                    "company": company.get("name", ""),
                    "cik": cik,
                    "form": form,
                    "filing_date": date,
                    "accession": accession,
                    "document": document,
                    "url": (f"https://www.sec.gov/Archives/edgar/data/"
                            f"{int(cik)}/{accession_no_dash}/{document}"),
                })
            successful_tickers += 1
            print("OK:", ticker, flush=True)
        except urllib.error.HTTPError as exc:
            errors.append({"ticker": ticker, "error": f"HTTP {exc.code}", "url": url})
            if exc.code in (403, 429):
                raise RuntimeError(
                    f"SEC access denied/rate limited (HTTP {exc.code}); "
                    "stop collection and preserve previous output"
                ) from exc
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            errors.append({"ticker": ticker, "error": str(exc), "url": url})
            print("ERROR:", ticker, str(exc), flush=True)
        time.sleep(0.2)

    if successful_tickers == 0:
        raise RuntimeError("No successful company responses; preserving previous SEC output")

    results.sort(key=lambda item: item["filing_date"], reverse=True)
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "SEC EDGAR",
        "data_type": "Official SEC filing metadata (not dilution analysis)",
        "status": "complete" if not errors else "partial",
        "watchlist_count": len(tickers),
        "successful_ticker_count": successful_tickers,
        "filing_count": len(results),
        "error_count": len(errors),
        "filings": results,
        "errors": errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(OUTPUT)
    print("TOTAL FILINGS:", len(results))
    print("ERRORS:", len(errors))
    print("SAVED:", OUTPUT)


if __name__ == "__main__":
    main()
