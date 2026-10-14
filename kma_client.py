"""KMA raw collection with explicit opt-in. No API call on import/check/setup.

The downloaded PCPH accumulation is NOT an instantaneous rain-rate GeoTIFF.
Only structurally valid ASCII is archived; georeferencing remains a separate gate.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parent
ENDPOINT = 'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-rdr_cmp1_api'
DOC = 'https://apihub.kma.go.kr/apiList.do?seqApi=5'
KST = timezone(timedelta(hours=9))
MAX_BYTES = 128 * 1024 * 1024


class ClientError(Exception):
    """Messages contain fixed diagnostics, never keys, URLs or response bodies."""

    def __init__(self, message, *, http_status=None):
        super().__init__(message)
        self.http_status = http_status


def env_values(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text('utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                raise ClientError('.env 형식 오류: NAME=value 형식으로 입력하세요.')
            name, value = line.split('=', 1)
            name, value = name.strip(), value.strip()
            if not re.fullmatch(r'[A-Z][A-Z0-9_]*', name):
                raise ClientError('.env 변수 이름 형식 오류')
            if value.startswith(('"', "'")):
                if len(value) < 2 or value[-1] != value[0]:
                    raise ClientError('.env 값의 따옴표를 닫아 주세요.')
                value = value[1:-1]
            values[name] = value
    # Explicit process environment overrides a local file, including a blank key.
    for name, value in os.environ.items():
        if name.startswith('KMA_') or name == 'QGIS_PYTHON':
            values[name] = value
    return values


@dataclass(frozen=True)
class Config:
    key: str = field(repr=False)
    timeout: int = 30
    attempts: int = 3
    poll: int = 300
    lag: int = 20
    accumulation: int = 60

    @classmethod
    def load(cls, root: Path | None = None) -> 'Config':
        root = root or ROOT
        values = env_values(root / '.env')
        def number(name, default, low, high):
            try:
                result = int(values.get(name, str(default)))
            except ValueError:
                raise ClientError(name + '에는 정수를 입력하세요.') from None
            if not low <= result <= high:
                raise ClientError(name + ' 설정 범위 오류')
            return result
        acc = number('KMA_ACCUMULATION_MINUTES', 60, 60, 1440)
        if acc % 60:
            raise ClientError('KMA_ACCUMULATION_MINUTES는 60의 배수여야 합니다.')
        return cls(values.get('KMA_API_KEY', '').strip(),
                   number('KMA_TIMEOUT_SECONDS', 30, 5, 120),
                   number('KMA_MAX_ATTEMPTS', 3, 1, 5),
                   number('KMA_POLL_SECONDS', 300, 300, 86400),
                   number('KMA_LAG_MINUTES', 20, 5, 1440), acc)


def request_time(value=None, config=None, now=None):
    if value is not None:
        if not re.fullmatch(r'\d{12}', value):
            raise ClientError('--time은 KST YYYYMMDDHHMM 형식입니다.')
        try:
            selected = datetime.strptime(value, '%Y%m%d%H%M').replace(tzinfo=KST)
        except ValueError:
            raise ClientError('유효하지 않은 KST 시각입니다.') from None
        if selected.minute % 5:
            raise ClientError('조회 시각은 5분 간격이어야 합니다.')
        if selected > (now or datetime.now(KST)):
            raise ClientError('미래 시각은 조회할 수 없습니다.')
        return value
    selected = (now or datetime.now(KST)) - timedelta(minutes=config.lag)
    selected = selected.replace(minute=selected.minute // 5 * 5, second=0, microsecond=0)
    return selected.strftime('%Y%m%d%H%M')


def parameters(config, tm):
    return {'tm': tm, 'cmp': 'PCPH', 'qcd': 'MSK', 'obs': 'ECHO',
            'acc': config.accumulation, 'map': 'HB', 'disp': 'A', 'unit': 'MM'}


def inspect_ascii(payload: bytes) -> dict:
    """Validate dimensions/count/order markers without inferring spatial alignment."""
    try:
        text = payload.decode('utf-8-sig')
    except UnicodeDecodeError:
        # KMA deployments can use legacy Korean comments. Data tokens remain ASCII.
        try:
            text = payload.decode('cp949')
        except UnicodeDecodeError:
            raise ClientError('응답 인코딩을 해석할 수 없습니다.') from None
    nx = ny = None
    count = 0
    negative = Counter()
    low = high = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'[\d\s,+\-=]+', line):
            raise ClientError('격자 ASCII가 아닌 응답입니다. 인증·활용신청·자료 시각을 확인하세요.')
        tokens = [v.strip() for v in line.replace('=', '').split(',') if v.strip()]
        if any(not re.fullmatch(r'[+-]?\d+', token) for token in tokens):
            raise ClientError('격자 응답에 정수가 아닌 값이 있습니다.')
        if nx is None:
            if len(tokens) != 2:
                raise ClientError('격자 크기 헤더가 없습니다.')
            nx, ny = map(int, tokens)
            if not (0 < nx <= 20000 and 0 < ny <= 20000 and nx * ny <= 20_000_000):
                raise ClientError('격자 크기가 허용 범위를 벗어났습니다.')
            continue
        for token in tokens:
            v = int(token)
            count += 1
            if count > nx * ny:
                raise ClientError('격자 값 개수가 헤더보다 많습니다.')
            if v < 0:
                negative[v] += 1
            else:
                low = v if low is None else min(low, v)
                high = v if high is None else max(high, v)
        if '=' in line and count % nx:
            raise ClientError('격자 행 종료 표시와 X축 개수가 일치하지 않습니다.')
    if nx is None or count != nx * ny:
        raise ClientError('격자 응답이 비어 있거나 중간에 끊겼습니다.')
    return {'nx': nx, 'ny': ny, 'value_count': count,
            'order': 'x_fastest_south_to_north',
            'negative_code_counts': dict(sorted(negative.items())),
            'encoded_nonnegative_min': low, 'encoded_nonnegative_max': high,
            'structural_validation': 'passed', 'spatial_alignment_verified': False,
            'observed_at_verified': False, 'nodata_semantics_verified': False}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # authKey must not be forwarded to a different endpoint.
        return None


def fetch_payload(config, params, opener=None, sleeper=time.sleep):
    if not config.key:
        raise ClientError('API 키가 비어 있습니다. 저장소 루트 .env의 KMA_API_KEY에 붙여 넣으세요.')
    opener = opener or build_opener(NoRedirect())
    # This authenticated URL remains private and is never logged or written to disk.
    request = Request(ENDPOINT + '?' + urlencode({**params, 'authKey': config.key}),
                      headers={'User-Agent': 'Halla-GeoData/1.0', 'Accept': 'text/plain'})
    message = '요청 실패'
    http_status = None
    for attempt in range(config.attempts):
        retry = False
        try:
            with opener.open(request, timeout=config.timeout) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ClientError('응답 크기 제한을 초과했습니다.')
            if config.key.encode() in payload:
                raise ClientError('응답에 인증정보가 포함되어 저장을 중단했습니다.')
            inspect_ascii(payload)
            return payload
        except HTTPError as exc:
            code = exc.code
            http_status = code
            exc.close()
            if code in (401, 403):
                message = f'HTTP {code} 인증/권한 응답: API허브 키·해당 레이더 활용신청·접근 제한을 확인하세요. 세부 원인은 이 상태 코드만으로 확정할 수 없습니다.'
            elif code == 429:
                message = 'HTTP 요청 한도 초과: 호출 주기와 계정 사용량을 확인하세요.'
                retry = True
            elif 500 <= code <= 599:
                message = 'HTTP 서버 오류: 기존 자료를 유지합니다.'
                retry = True
            elif 300 <= code <= 399:
                message = 'HTTP 리다이렉트를 차단했습니다. 공식 문서의 주소를 확인하세요.'
            else:
                message = 'HTTP 요청 오류: 요청 조건·자료 시각·활용신청을 확인하세요.'
        except (URLError, TimeoutError, OSError):
            http_status = None
            message = '네트워크/시간초과 오류: DNS·프록시·방화벽·연결 상태를 확인하세요.'
            retry = True
        if not retry or attempt + 1 == config.attempts:
            raise ClientError(message, http_status=http_status) from None
        sleeper(min(2 ** attempt * 2, 30))
    raise ClientError(message)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='write-', suffix='.tmp', dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        for attempt in range(8):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(min(.1 * 2 ** attempt, 1))
    finally:
        temp.unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8'))


def collect(config, tm, root=ROOT, opener=None, sleeper=time.sleep):
    params = parameters(config, tm)
    folder = root / 'runtime/kma/raw'
    # Hash distinguishes corrections at the same requested time without overwriting.
    payload = fetch_payload(config, params, opener, sleeper)
    summary = inspect_ascii(payload)
    digest = hashlib.sha256(payload).hexdigest()
    filename = f'PCPH_MSK_MM_{config.accumulation}min_{tm}_{digest[:12]}.txt'
    path = folder / filename
    if not path.exists():
        atomic_write(path, payload)
    manifest = {'schema_version': 1, 'status': 'raw_collected', 'requested_at_kst': tm,
                'collected_at_utc': datetime.now(timezone.utc).isoformat(),
                'endpoint_without_key': ENDPOINT, 'documentation': DOC,
                'parameters_without_key': params, 'sha256': digest,
                'bytes': len(payload), 'file': filename, 'grid': summary,
                'documented_quantity': 'precipitation_accumulation',
                'documented_unit': 'mm', 'documented_scale': .01,
                'map_ready': False,
                'next_step': '실제 응답의 좌표·시각·결측 검증 및 누적강수 지도 입력기 필요. mm/h로 넣지 마세요.'}
    write_json(path.with_suffix('.json'), manifest)
    # This raw pointer is separate from the map's verified latest.json.
    write_json(root/'runtime/kma/latest_raw.json', manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'check', 'fetch', 'watch'])
    parser.add_argument('--time', help='fetch only: YYYYMMDDHHMM, KST')
    args = parser.parse_args(argv)
    try:
        if args.command == 'setup':
            path = ROOT / '.env'
            if not path.exists():
                # Exclusive mode prevents overwriting an existing user's key.
                with path.open('x', encoding='utf-8') as stream:
                    stream.write((ROOT/'.env.example').read_text('utf-8'))
            print('.env 준비 완료. 기존 값은 유지했습니다. API 호출 없음.')
            return 0
        config = Config.load()
        if args.command == 'check':
            print(json.dumps({'key_configured': bool(config.key), 'network_called': False,
                              'product': 'PCPH', 'quantity': '누적강수량 mm',
                              'accumulation_minutes': config.accumulation,
                              'poll_seconds': config.poll, 'map_adapter': 'pending_verification'}, ensure_ascii=False))
            return 0
        if not config.key:
            raise ClientError('API 키가 비어 있습니다. .env의 KMA_API_KEY에 API허브 키를 입력하세요.')
        if args.time and args.command != 'fetch':
            raise ClientError('--time은 fetch 명령에서만 사용할 수 있습니다.')
        while True:
            tm = request_time(args.time, config)
            try:
                record = collect(config, tm)
                print('원자료 저장 완료: ' + record['file'] + ' / 지도 변환 전', flush=True)
                write_json(ROOT/'runtime/kma/status.json', {'status': 'raw_collected', 'requested_at_kst': tm})
            except ClientError as exc:
                write_json(ROOT/'runtime/kma/status.json', {
                    'status': 'error', 'requested_at_kst': tm,
                    'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                    'http_status': exc.http_status, 'message': str(exc)})
                if args.command != 'watch':
                    raise
                print(str(exc), file=sys.stderr, flush=True)
            if args.command != 'watch':
                return 0
            time.sleep(config.poll)
    except ClientError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('수집 중지. 기존 원자료와 지도는 유지합니다.')
        return 0
    except OSError:
        # OS error objects may carry paths; don't dump arbitrary internals.
        print('로컬 파일 읽기/쓰기 실패: 저장 공간과 폴더 권한을 확인하세요.', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
