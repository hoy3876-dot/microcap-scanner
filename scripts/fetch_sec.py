
import json
import os
import time
import urllib.requestimport urllib.error
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
WATCHLIST = BASE / "data" / "sec_watchlist.txt"
OUTPUT = BASE / "data" / "sec_filings.json"

# SEC 공식 무료 데이터
HEADERS = {
    "User-Agent": os.getenv(
        "SEC_USER_AGENT",
        "MicrocapScanner/0.6 (contact: hoy3876l@naver.com)"
    ),
    "Accept-Encoding": "gzip, deflate",
}

TARGET_FORMS = {
    "S-1", "S-3", "F-1", "F-3",
    "424B1", "424B2", "424B3", "424B4", "424B5",
    "8-K", "6-K", "10-K", "10-Q",
    "SC 13D", "SC 13G", "13D", "13G",
    "DEF 14A", "PRE 14A", "EFFECT",
    "4", "3", "5"
}


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    if not WATCHLIST.exists():
        print("SEC watchlist not found:", WATCHLIST)
        print("Create data/sec_watchlist.txt with one ticker per line.")
        return

    tickers = [
        x.strip().upper()
        for x in WATCHLIST.read_text(encoding="utf-8").splitlines()
        if x.strip() and not x.startswith("#")
    ]

    tickers = list(dict.fromkeys(tickers))[:100]

    print("Watchlist:", len(tickers))

    mapping = get_json(
        "https://www.sec.gov/files/company_tickers.json"
    )

    ticker_to_cik = {
        item["ticker"].upper(): str(item["cik_str"]).zfill(10)
        for item in mapping.values()
    }

    results = []
    errors = []

    for ticker in tickers:
        cik = ticker_to_cik.get(ticker)

        if not cik:
            errors.append({
                "ticker": ticker,
                "error": "SEC CIK not found"
            })
            continue

        try:
            url = (
                "https://data.sec.gov/submissions/CIK"
                + cik + ".json"
            )

            company = get_json(url)
            recent = company.get("filings", {}).get(
                "recent", {}
            )

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            documents = recent.get("primaryDocument", [])

            company_name = company.get("name", "")

            for i, form in enumerate(forms):
                if form not in TARGET_FORMS:
                    continue

                accession = accessions[i].replace("-", "")
                document = documents[i]

                results.append({
                    "ticker": ticker,
                    "company": company_name,
                    "cik": cik,
                    "form": form,
                    "filing_date": dates[i],
                    "accession": accessions[i],
                    "document": document,
                    "url": (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{int(cik)}/{accession}/{document}"
                    )
                })

            print("OK:", ticker)

        except Exception as e:
            errors.append({
                "ticker": ticker,
                "error": str(e)
            })
            print("ERROR:", ticker, str(e))

        time.sleep(0.15)

    results.sort(
        key=lambda x: x["filing_date"],
        reverse=True
    )

    data = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": "SEC EDGAR",
        "data_type": "Official SEC filing metadata",
        "watchlist_count": len(tickers),
        "filing_count": len(results),
        "error_count": len(errors),
        "filings": results,
        "errors": errors
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("TOTAL FILINGS:", len(results))
    print("ERRORS:", len(errors))
    print("SAVED:", OUTPUT)


if __name__ == "__main__":
    main()
