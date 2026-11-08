"""Best-effort delayed daily quotes for a small SEC watchlist. No live feed or guaranteed coverage."""
import csv, json, pathlib, datetime, time
from urllib.request import Request, urlopen
ROOT=pathlib.Path(__file__).resolve().parents[1]
WATCH=ROOT/'data'/'sec_watchlist.txt'
OUT=ROOT/'data'/'free_quotes.json'
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
rows=[]; errors=[]
tickers=[x.strip().upper() for x in WATCH.read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')][:100] if WATCH.exists() else []
try:
 import yfinance as yf
except ImportError as e:
 raise SystemExit('Install yfinance: '+str(e))
for ticker in tickers:
 try:
  hist=yf.Ticker(ticker).history(period='2mo',interval='1d',auto_adjust=False)
  hist=hist.dropna(subset=['Close','Volume'])
  if hist.empty: raise ValueError('no daily bars')
  last=hist.iloc[-1]; vol=float(last['Volume']); prior=hist['Volume'].iloc[-21:-1]
  avg=float(prior.mean()) if len(prior)>=10 else 0
  rvol=round(vol/avg,2) if avg>0 else None
  rows.append({'ticker':ticker,'price':round(float(last['Close']),4),'volume':int(vol),'rvol':rvol,'float':None,'sector':None,'asof':str(hist.index[-1].date())})
 except Exception as e: errors.append({'ticker':ticker,'error':str(e)[:160]})
 time.sleep(.3)
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({'generated_at':now,'source':'Yahoo Finance via unofficial yfinance; delayed daily bars; coverage not guaranteed','universe':'first 100 symbols in data/sec_watchlist.txt','rows':rows,'errors':errors},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('rows',len(rows),'errors',len(errors))
