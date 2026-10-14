"""Fetch the current KMA weather warnings (특보 현황) for Jeju and write them for the dashboard.

Run with plain Python (HTTPS):  python work/fetch_kma_warnings.py
Reads KMA_API_KEY from .env (same key as kma_client.py). Endpoint: API Hub 예특보 > 특보 현황,
  https://apihub.kma.go.kr/api/typ01/url/wrn_now_data.php?fe=f&tm=<KST YYYYMMDDHHMM>&disp=0&help=1
The API needs its own 활용신청; until approved the hub answers HTTP 403 and this script records
status "not_authorized" so the dashboard can say so instead of showing nothing.

Output
  runtime/kma/warnings/<tm>.txt                 raw response (never committed)
  runtime/kma/warnings/latest.json              parsed status
  outputs/jeju_dashboard/data/warnings.json     the same, for the static site / standalone build
The parser is tolerant: it keeps every data row as a list of fields and the header names the API prints
with help=1, and filters rows whose region text contains 제주. Field meaning must be re-checked against the
first real response (the format was not observable before approval).
"""
from pathlib import Path
import datetime as dt, json, re, sys, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from region_config import ROOT

KST = dt.timezone(dt.timedelta(hours=9))
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/url/wrn_now_data.php'
WRN_NAMES = {'W': '강풍', 'R': '호우', 'C': '한파', 'D': '건조', 'O': '해일', 'N': '지진해일', 'V': '풍랑', 'T': '태풍', 'S': '대설', 'Y': '황사', 'H': '폭염', 'F': '안개'}
LVL_NAMES = {'1': '예비', '2': '주의보', '3': '경보'}


def key_from_env():
    for line in (ROOT / '.env').read_text('utf-8-sig').splitlines():
        if line.strip().startswith('KMA_API_KEY='):
            return line.split('=', 1)[1].strip()
    return ''


def parse(text):
    headers, rows = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('#'):
            body = s.lstrip('#').strip()
            if ',' in body and re.search(r'[A-Z_]{2,}', body) and not headers:
                headers = [h.strip() for h in body.split(',') if h.strip()]
            continue
        fields = [f.strip() for f in s.rstrip('=').split(',')]
        if len(fields) >= 3:
            rows.append(fields)
    return headers, rows


def main():
    key = key_from_env()
    now = dt.datetime.now(KST); tm = now.strftime('%Y%m%d%H%M')
    out_dir = ROOT / 'runtime/kma/warnings'; out_dir.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 1, 'checked_at': now.isoformat(), 'endpoint': ENDPOINT, 'region_filter': '제주', 'status': 'error', 'message': '', 'jeju': [], 'all_rows': 0, 'headers': []}
    if not key:
        result.update(status='no_key', message='.env의 KMA_API_KEY가 비어 있습니다')
    else:
        url = ENDPOINT + '?' + urllib.parse.urlencode({'fe': 'f', 'tm': tm, 'disp': '0', 'help': '1', 'authKey': key})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Halla-GeoData/1.0'}), timeout=60) as r:
                raw = r.read(); code = r.status
        except urllib.error.HTTPError as e:
            raw = e.read(2000); code = e.code
        except Exception as e:
            raw = b''; code = None; result['message'] = '네트워크 오류: ' + type(e).__name__
        text = raw.decode('utf-8', 'replace') if raw else ''
        if key in text:
            text = text.replace(key, '<KEY>')
        if code == 200 and raw:
            (out_dir / f'{tm}.txt').write_text(text, encoding='utf-8')
            headers, rows = parse(text)
            jeju = []
            for fields in rows:
                joined = ' '.join(fields)
                if '제주' in joined:
                    rec = {'fields': fields}
                    if headers and len(headers) == len(fields):
                        rec['by_name'] = dict(zip(headers, fields))
                        wrn = rec['by_name'].get('WRN', ''); lvl = rec['by_name'].get('LVL', '')
                        rec['warning'] = WRN_NAMES.get(wrn, wrn); rec['level'] = LVL_NAMES.get(lvl, lvl)
                    jeju.append(rec)
            result.update(status='ok', message=f'특보 {len(jeju)}건 (제주 관련) / 전체 {len(rows)}행', jeju=jeju, all_rows=len(rows), headers=headers)
        elif code in (401, 403):
            result.update(status='not_authorized', message='특보 API 활용신청이 필요합니다 (HTTP %s). API허브 > 예특보 > 특보 메뉴에서 신청하세요.' % code)
        elif code:
            result.update(status='error', message=f'HTTP {code}: ' + re.sub(r'\s+', ' ', text)[:200])
    for target in [out_dir / 'latest.json', ROOT / 'outputs/jeju_dashboard/data/warnings.json']:
        target.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['status', 'message', 'all_rows']}, ensure_ascii=False))
    return 0 if result['status'] in ('ok', 'not_authorized') else 2


if __name__ == '__main__':
    raise SystemExit(main())
