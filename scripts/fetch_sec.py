import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'data'
WATCHLIST = DATA / 'sec_watchlist.txt'
OUTPUT = DATA / 'sec_filings.json'
CIK_CACHE = DATA / 'sec_cik_map.json'
TARGET_FORMS = {'S-1','S-3','F-1','F-3','424B1','424B2','424B3','424B4','424B5','8-K','6-K','10-K','10-Q','SC 13D','SC 13G','13D','13G','DEF 14A','PRE 14A','EFFECT','4','3','5'}

def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}

def get_json(url):
    agent = os.getenv('SEC_USER_AGENT', 'MicrocapScanner/0.7 (contact: hoy3876l@naver.com)').strip()
    if '\n' in agent or '\r' in agent:
        raise ValueError('SEC_USER_AGENT contains a newline')
    request = urllib.request.Request(url, headers={'User-Agent':agent,'Accept':'application/json','Accept-Encoding':'identity'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        print(f'SEC HTTP ERROR: {exc.code}; REQUEST URL: {url}; RETRY AFTER: {exc.headers.get("Retry-After", "not provided")}', flush=True)
        raise

def main():
    if not WATCHLIST.exists():
        raise SystemExit('Missing data/sec_watchlist.txt')
    tickers = list(dict.fromkeys(x.strip().upper() for x in WATCHLIST.read_text(encoding='utf-8').splitlines() if x.strip() and not x.lstrip().startswith('#')))[:100]
    print('Watchlist:', len(tickers), flush=True)
    old = read_json(OUTPUT)
    mapping = {}
    cache = read_json(CIK_CACHE)
    for ticker, cik in cache.items():
        if str(cik).isdigit():
            mapping[ticker.upper()] = str(cik).zfill(10)
    for item in old.get('filings', []):
        ticker, cik = item.get('ticker'), str(item.get('cik', ''))
        if ticker and cik.isdigit():
            mapping.setdefault(ticker.upper(), cik.zfill(10))
    missing = [t for t in tickers if t not in mapping]
    if missing:
        try:
            remote = get_json('https://www.sec.gov/files/company_tickers.json')
            for item in remote.values():
                ticker, cik = item.get('ticker'), item.get('cik_str')
                if ticker and str(cik).isdigit():
                    mapping[ticker.upper()] = str(cik).zfill(10)
        except Exception as exc:
            print('CIK download unavailable; using cached CIK only:', exc, flush=True)
    results, errors, successes = [], [], 0
    for ticker in tickers:
        cik = mapping.get(ticker)
        if not cik:
            errors.append({'ticker':ticker,'error':'CIK unverified/unavailable'})
            continue
        try:
            company = get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')
            recent = company.get('filings', {}).get('recent', {})
            forms = recent.get('form', [])
            dates = recent.get('filingDate', [])
            accessions = recent.get('accessionNumber', [])
            documents = recent.get('primaryDocument', [])
            for form, date, accession, document in zip(forms, dates, accessions, documents):
                if form not in TARGET_FORMS:
                    continue
                results.append({'ticker':ticker,'company':company.get('name',''),'cik':cik,'form':form,'filing_date':date,'accession':accession,'document':document,'url':f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/{document}'})
            successes += 1
            print('OK:', ticker, flush=True)
        except Exception as exc:
            errors.append({'ticker':ticker,'error':str(exc)})
            print('ERROR:', ticker, exc, flush=True)
        time.sleep(0.2)
    if successes == 0:
        print('NO VERIFIED SUCCESS: preserving existing SEC data. Errors:', json.dumps(errors), flush=True)
        raise SystemExit(1)
    # Never overwrite a previously successful snapshot with an incomplete refresh.
    if errors:
        print('PARTIAL REFRESH: preserving existing SEC data. Errors:', json.dumps(errors), flush=True)
        raise SystemExit(1)
    results.sort(key=lambda x:x['filing_date'], reverse=True)
    payload = {'generated_at':datetime.now(timezone.utc).isoformat(),'source':'SEC EDGAR','data_type':'Official SEC filing metadata','watchlist_count':len(tickers),'filing_count':len(results),'error_count':0,'filings':results,'errors':[]}
    DATA.mkdir(parents=True, exist_ok=True)
    temp = OUTPUT.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(OUTPUT)
    CIK_CACHE.write_text(json.dumps({t:mapping[t] for t in tickers if t in mapping}, indent=2), encoding='utf-8')
    print('SAVED:', OUTPUT, 'FILINGS:', len(results), flush=True)

if __name__ == '__main__':
    main()
