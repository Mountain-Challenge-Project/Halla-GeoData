"""Bounded Jeju weather collection. Credentials are loaded locally, never logged."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote, quote_plus
from urllib.request import Request, build_opener

from kma_client import Config, NoRedirect

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "runtime" / "jeju_weather_collection"
KST = timezone(timedelta(hours=9))
BASE = "https://apihub.kma.go.kr"
LOG_LOCK = threading.Lock()

ASOS_FIELDS = "TM STN WD WS GST_WD GST_WS GST_TM PA PS PT PR TA TD HM PV RN RN_DAY RN_JUN RN_INT SD_HR3 SD_DAY SD_TOT WC WP WW CA_TOT CA_MID CH_MIN CT CT_TOP CT_MID CT_LOW VS SS SI ST_GD TS TE_005 TE_01 TE_02 TE_03 ST_SEA WH BF IR IX".split()
AWS_FIELDS = "TM STN WD1 WS1 WDS WSS WD10 WS10 TA RE RN_15m RN_60m RN_12h RN_DAY HM PA PS TD".split()


def parse_aws(payload):
    rows = []
    for line in data_lines(payload):
        t = [v.strip() for v in line.strip().rstrip(",=").split(",")]
        if len(t) != len(AWS_FIELDS) or not re.fullmatch(r"\d{12}", t[0]):
            raise ValueError("AWS minute schema mismatch")
        row = dict(zip(AWS_FIELDS, t))
        for field in AWS_FIELDS[2:]:
            float(row[field])
        rows.append(row)
    if not rows or "#7777END" not in decode(payload):
        raise ValueError("AWS empty or incomplete response")
    return rows


def data_lines(payload):
    return [s.strip().rstrip("=") for s in decode(payload).splitlines() if s.strip() and not s.lstrip().startswith("#")]


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if not rows and not fields:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def parse_stations(payload, inf, reference_time):
    rows = []
    for line in data_lines(payload):
        if "제주특별자치도" not in line:
            continue
        t = line.split()
        if inf == "SFC":
            row = dict(station_id=t[0], longitude=float(t[1]), latitude=float(t[2]),
                       station_code=t[3], ground_elevation_m=float(t[4]),
                       barometer_elevation_m=float(t[5]), thermometer_height_agl_m=float(t[6]),
                       wind_height_agl_m=float(t[7]), raingauge_height_agl_m=float(t[8]),
                       name=t[10], forecast_zone=t[12], law_id=t[13])
        else:
            row = dict(station_id=t[0], longitude=float(t[1]), latitude=float(t[2]),
                       station_code=t[3], ground_elevation_m=float(t[4]),
                       barometer_elevation_m="", thermometer_height_agl_m="",
                       wind_height_agl_m=float(t[5]), raingauge_height_agl_m="",
                       name=t[8], forecast_zone=t[10], law_id=t[11])
        row.update(network=inf, metadata_reference_kst=reference_time,
                   metadata_history_verified=False,
                   source_url=BASE + "/api/typ01/url/stn_inf.php")
        rows.append(row)
    if not rows:
        raise ValueError("No Jeju stations in metadata response")
    return rows


def parse_asos(payload):
    rows = []
    for line in data_lines(payload):
        t = line.split()
        if len(t) != len(ASOS_FIELDS) or not re.fullmatch(r"\d{12}", t[0]):
            raise ValueError("ASOS schema mismatch")
        row = dict(zip(ASOS_FIELDS, t))
        moment = datetime.strptime(row["TM"], "%Y%m%d%H%M").replace(tzinfo=KST)
        row.update(observed_at_kst=moment.isoformat(), observed_at_utc=moment.astimezone(timezone.utc).isoformat())
        rows.append(row)
    if not rows or "#7777END" not in decode(payload):
        raise ValueError("ASOS empty response")
    return rows


def parse_daily(payload, variable):
    rows = []
    for line in data_lines(payload):
        t = [s.strip() for s in line.split(",")]
        if len(t) < 6 or not re.fullmatch(r"\d{8}", t[0]):
            raise ValueError("Daily schema mismatch")
        raw = float(t[5])
        invalid = raw <= -90 or (variable.startswith(("rn", "ws")) and raw < 0)
        rows.append(dict(date_kst=datetime.strptime(t[0], "%Y%m%d").date().isoformat(), station_id=t[1],
                         longitude=float(t[2]), latitude=float(t[3]), ground_elevation_m=float(t[4]),
                         variable=variable, value_raw=t[5], value="" if invalid else raw,
                         qc="suspect_missing_code" if invalid else "not_independently_validated",
                         unit="mm" if variable == "rn_day" else "m/s" if variable.startswith("ws") else "degC",
                         station_name=t[6] if len(t)>6 else ""))
    if not rows:
        raise ValueError("Daily empty response")
    return rows


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def decode(data):
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


class Collector:
    def __init__(self, output=OUT, timeout=25):
        self.output = Path(output)
        self.key = Config.load(ROOT).key
        self.timeout = timeout
        self.opener = None
        self.log = []
        self.consecutive_network_failures = 0

    def fetch(self, name, endpoint, params, authenticated=True):
        safe_url = endpoint if endpoint.startswith("https://") else BASE + endpoint
        safe_params = dict(params)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        entry = dict(dataset=name, requested_at_utc=stamp, endpoint=safe_url,
                     parameters=safe_params, http_status=None, status="pending")
        if self.consecutive_network_failures >= 3:
            entry["status"] = "skipped_network_circuit_open"
            self.record(entry)
            return None
        if authenticated and not self.key:
            entry["status"] = "missing_key"
            self.record(entry)
            return None
        query = {**params, **({"authKey": self.key} if authenticated else {})}
        request = Request(safe_url + ("?" + urlencode(query) if query else ""),
                          headers={"User-Agent": "Halla-GeoData research collector/1.0"})
        started = time.monotonic()
        try:
            if self.opener is None:
                self.opener = build_opener(NoRedirect())
            with self.opener.open(request, timeout=self.timeout) as response:
                entry["http_status"] = response.status
                entry["content_type"] = response.headers.get("Content-Type", "")
                payload = response.read(128 * 1024 * 1024 + 1)
            if len(payload) > 128 * 1024 * 1024:
                entry["status"] = "response_too_large"
                return None
            variants = (self.key, quote(self.key,safe=""), quote_plus(self.key)) if self.key else ()
            if any(v.encode() in payload for v in variants):
                entry["status"] = "credential_echo_blocked"
                return None
            path = self.output / "raw" / name / (stamp + ".txt")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            entry.update(status="downloaded_unvalidated", bytes=len(payload),
                         sha256=hashlib.sha256(payload).hexdigest(), raw_path=path.relative_to(self.output).as_posix())
            self.consecutive_network_failures = 0
            return payload
        except HTTPError as exc:
            entry.update(http_status=exc.code, status="http_error")
            exc.close()
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            reason = getattr(exc,"reason",exc)
            entry.update(status="network_error", error_type=type(exc).__name__,
                         network_error_code=getattr(reason,"winerror",None) or getattr(reason,"errno",None))
            self.consecutive_network_failures += 1
        finally:
            entry["elapsed_seconds"] = round(time.monotonic() - started, 2)
            entry["received_at_utc"] = datetime.now(timezone.utc).isoformat()
            self.record(entry)
        return None

    def record(self, entry):
        self.log.append(entry)
        self.output.mkdir(parents=True, exist_ok=True)
        with LOG_LOCK:
            with (self.output / "requests.jsonl").open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(json.dumps({k: entry[k] for k in ("dataset", "status", "http_status", "bytes", "elapsed_seconds") if k in entry}), flush=True)

    def probe(self):
        now = datetime.now(KST) - timedelta(minutes=30)
        tm = now.strftime("%Y%m%d%H00")
        for inf in ("SFC", "AWS"):
            self.fetch("station_" + inf.lower(), "/api/typ01/url/stn_inf.php", dict(inf=inf, stn=0, tm=tm, help=1))
        self.fetch("asos_probe", "/api/typ01/url/kma_sfctm3.php", dict(tm1="202610150000", tm2="202610150200", stn=184, help=1))
        self.fetch("aws_latest_probe", "/api/typ01/cgi-bin/url/nph-aws2_min", dict(tm2=tm, stn=0, disp=1, help=1))
        self.fetch("aws_daily_probe", "/api/typ01/url/sfc_aws_day.php", dict(tm1="20261014", tm2="20261015", obs="rn_day", stn=184, help=1))
        self.fetch("forecast_coordinate", "/api/typ01/cgi-bin/url/nph-dfs_xy_lonlat", dict(lon=126.5357, lat=33.361, help=1))

    def cached_payload(self, name):
        files = sorted((self.output / "raw" / name).glob("*.txt"))
        return files[-1].read_bytes() if files else None

    def stations(self, refresh=False):
        result = {}
        tm = datetime.now(KST).strftime("%Y%m%d%H%M")
        for inf in ("SFC", "AWS"):
            payload = None if refresh else self.cached_payload("station_" + inf.lower())
            if payload is None:
                payload = self.fetch("station_" + inf.lower(), "/api/typ01/url/stn_inf.php", dict(inf=inf, stn=0, tm=tm, help=1))
            if payload:
                entries = [json.loads(s) for s in (self.output / "requests.jsonl").read_text("utf-8").splitlines()]
                original = next((e for e in reversed(entries) if e["dataset"] == "station_" + inf.lower() and e.get("raw_path")), {})
                reference = original.get("parameters", {}).get("tm", tm)
                result[inf] = parse_stations(payload, inf, reference)
                write_csv(self.output / "csv" / ("stations_" + inf.lower() + ".csv"), result[inf])
        return result

    def history(self, start, end):
        begin = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=KST)
        finish = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=KST)
        if not 0 <= (finish-begin).days < 31 or finish.date() >= datetime.now(KST).date():
            raise ValueError("History requires 1-31 complete past days")
        stations = self.stations()
        sfc = ":".join(r["station_id"] for r in stations["SFC"])
        aws = ":".join(r["station_id"] for r in stations["AWS"])
        params = dict(tm1=begin.strftime("%Y%m%d0000"), tm2=finish.strftime("%Y%m%d2300"), stn=sfc, help=1)
        tag = begin.strftime("%Y%m%d") + "_" + finish.strftime("%Y%m%d")
        name = "asos_hourly_" + tag
        payload = self.cached_payload(name) or self.fetch(name, "/api/typ01/url/kma_sfctm3.php", params)
        if payload:
            rows = parse_asos(payload)
            write_csv(self.output / "csv" / (name + "_raw.csv"), rows)
            print(json.dumps(dict(dataset=name, parsed_rows=len(rows))), flush=True)
        daily_rows = []
        for variable in ("rn_day", "ta_max", "ta_min", "ws_max", "ws_ins_max"):
            name = "aws_daily_" + variable + "_" + tag
            payload = self.cached_payload(name) or self.fetch(name, "/api/typ01/url/sfc_aws_day.php",
                       dict(tm1=begin.strftime("%Y%m%d"), tm2=finish.strftime("%Y%m%d"), obs=variable, stn=aws, help=1))
            if payload:
                daily_rows.extend(parse_daily(payload, variable))
        write_csv(self.output / "csv" / ("aws_daily_" + tag + ".csv"), daily_rows)
        print(json.dumps(dict(dataset="aws_daily", parsed_rows=len(daily_rows))), flush=True)

    def latest(self):
        stations = self.stations()
        now = datetime.now(KST) - timedelta(minutes=10)
        tm = now.strftime("%Y%m%d%H00")
        sfc = ":".join(r["station_id"] for r in stations["SFC"])
        self.fetch("asos_latest", "/api/typ01/url/kma_sfctm2.php", dict(tm=tm, stn=sfc, help=1))
        minute_tm = now.strftime("%Y%m%d%H%M")
        payload = self.fetch("aws_minute_latest", "/api/typ01/cgi-bin/url/nph-aws2_min", dict(tm2=minute_tm, stn=0, disp=1, help=1))
        if payload is None and self.log[-1].get("http_status") not in (401,403,429) and self.consecutive_network_failures < 3:
            for station in stations["AWS"]:
                self.fetch("aws_latest_" + station["station_id"], "/api/typ01/cgi-bin/url/nph-aws2_min", dict(tm2=minute_tm, stn=station["station_id"], disp=1, help=1))
                if self.log[-1].get("http_status") in (401,403,429) or self.consecutive_network_failures >= 3:
                    break
                time.sleep(0.15)
        issued = datetime.now(KST)-timedelta(minutes=45)
        issued = issued.replace(minute=issued.minute//30*30, second=0, microsecond=0)
        self.fetch("ultra_forecast", "/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtFcst",
                   dict(pageNo=1, numOfRows=1000, dataType="JSON", base_date=issued.strftime("%Y%m%d"), base_time=issued.strftime("%H%M"), nx=54, ny=36))
        short_issued = datetime.now(KST) - timedelta(hours=1)
        short_issued = short_issued.replace(hour=((short_issued.hour+1)//3)*3-1 if short_issued.hour>=2 else 23, minute=0, second=0, microsecond=0)
        if short_issued > datetime.now(KST)-timedelta(hours=1):
            short_issued -= timedelta(days=1)
        self.fetch("short_forecast", "/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst",
                   dict(pageNo=1, numOfRows=2000, dataType="JSON", base_date=short_issued.strftime("%Y%m%d"), base_time=short_issued.strftime("%H%M"), nx=54, ny=36))

    def mountain_history(self, start, end, limit=None, workers=2, station_subset=None):
        begin = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=KST)
        finish = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=KST)
        if not 0 <= (finish-begin).days < 31 or finish.date() >= datetime.now(KST).date():
            raise ValueError("History requires 1-31 complete past days")
        stations = station_subset if station_subset is not None else [s for s in self.stations()["AWS"] if s["ground_elevation_m"] >= 700]
        if limit:
            stations = stations[:limit]
        if workers > 1 and len(stations) > 1:
            def collect_station(station):
                worker = Collector(self.output, self.timeout)
                worker.mountain_history(start, end, workers=1, station_subset=[station])
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(collect_station, stations))
            return
        for station in (stations[:limit] if limit else stations):
            rows = []
            day = begin
            while day <= finish:
                tag = day.strftime("%Y%m%d")
                name = "aws_minute_" + station["station_id"] + "_" + tag
                part = self.aws_period(name, day, day.replace(hour=23,minute=59), station["station_id"])
                if part is None:
                    return
                rows.extend(part)
                day += timedelta(days=1)
            write_csv(self.output / "csv" / ("aws_minute_" + station["station_id"] + "_" + begin.strftime("%Y%m%d") + "_" + finish.strftime("%Y%m%d") + "_raw.csv"), rows)
            print(json.dumps(dict(station=station["station_id"], parsed_minutes=len(rows))), flush=True)

    def aws_period(self, name, begin, end, station_id):
        payload = self.cached_payload(name)
        # A malformed cached small chunk must not permanently prevent a retry.
        if payload is not None and (end-begin).total_seconds() <= 6*3600:
            try:
                parse_aws(payload)
            except ValueError:
                payload = None
        if payload is None:
            payload = self.fetch(name, "/api/typ01/cgi-bin/url/nph-aws2_min",
                                 dict(tm1=begin.strftime("%Y%m%d%H%M"), tm2=end.strftime("%Y%m%d%H%M"), stn=station_id, disp=1, help=1))
            if self.log[-1].get("http_status") in (401,403,429) or self.consecutive_network_failures >= 3:
                return None
            time.sleep(0.2)
        if payload:
            try:
                part = parse_aws(payload)
                low, high = begin.strftime("%Y%m%d%H%M"), end.strftime("%Y%m%d%H%M")
                if any(r["STN"] != station_id or not low <= r["TM"] <= high for r in part):
                    raise ValueError("Returned station/time differs from request")
                return part
            except ValueError:
                pass
        if (end-begin).total_seconds() > 6*3600:
            rows = []
            moment = begin
            while moment <= end:
                stop = min(moment+timedelta(hours=6)-timedelta(minutes=1),end)
                part = self.aws_period(name+"_h"+moment.strftime("%H"),moment,stop,station_id)
                if part is None:
                    return None
                rows.extend(part)
                moment = stop+timedelta(minutes=1)
            return rows
        print(json.dumps(dict(dataset=name,validation_error="Incomplete response; retained raw; excluded from CSV")),flush=True)
        return []

    def extended(self):
        now = datetime.now(KST) - timedelta(minutes=40)
        tm = now.strftime("%Y%m%d%H%M")
        self.fetch("aws_summit_probe", "/api/typ01/cgi-bin/url/nph-aws2_min", dict(tm2=tm, stn=871, disp=1, help=1))
        utc = datetime.now(timezone.utc)-timedelta(hours=3)
        utc = utc.replace(hour=12 if utc.hour >= 12 else 0, minute=0, second=0, microsecond=0)
        self.fetch("sounding_latest", "/api/typ01/url/upp_temp.php", dict(tm=utc.strftime("%Y%m%d%H%M"), stn=0, pa=0, help=1))
        self.fetch("sounding_indices_30days", "/api/typ01/url/upp_idx.php", dict(tm1="202609160000", tm2="202610151200", stn=0, help=1))
        satellite_end = datetime.now(timezone.utc)-timedelta(hours=2)
        satellite_start = satellite_end-timedelta(hours=3)
        self.fetch("satellite_cloud_point", "/api/typ01/cgi-bin/url/nph_sun_sat_txt",
                   dict(tm1=satellite_start.strftime("%Y%m%d%H00"), tm2=satellite_end.strftime("%Y%m%d%H00"), int=60, varn="CA", lon=126.5357, lat=33.361))

    def radar(self):
        from kma_client import request_time, parameters, inspect_ascii
        config = Config.load(ROOT)
        tm = request_time(config=config)
        payload = self.fetch("radar_latest", "/api/typ01/cgi-bin/url/nph-rdr_cmp1_api", parameters(config, tm))
        if payload:
            try:
                validation = inspect_ascii(payload)
                validation.update(requested_time_kst=tm, accumulation_minutes=config.accumulation,
                                  unit="encoded mm*100", conversion="nonnegative value * 0.01 = mm; negative codes unresolved")
                save_json(self.output / "radar_validation.json", validation)
            except Exception:
                save_json(self.output / "radar_validation.json", {"structural_validation":"failed"})
        if self.cached_payload("radar_coordinates_netcdf") is None:
            self.fetch("radar_coordinates_netcdf", "/api/typ01/url/rdr_latlon_file_down.php", dict(cmp="PCP"))

    def sounding_history(self, start, end):
        begin = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=KST)
        finish = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=KST)
        if not 0 <= (finish-begin).days < 31 or finish.date() >= datetime.now(KST).date():
            raise ValueError("History requires 1-31 complete past days")
        day = begin
        while day <= finish:
            for hour in (3,9,15,21):
                utc = day.replace(hour=hour).astimezone(timezone.utc)
                tag = utc.strftime("%Y%m%d%H%M")
                name = "sounding_47186_" + tag
                if self.cached_payload(name) is None:
                    self.fetch(name, "/api/typ01/url/upp_temp.php", dict(tm=tag, stn=47186, pa=0, help=1))
                    if self.log[-1].get("http_status") in (401,403,429) or self.consecutive_network_failures >= 3:
                        return
                    time.sleep(0.25)
            day += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["probe", "history", "latest", "refresh", "export", "extended", "mountain-history", "sounding-history", "radar", "coordinates"])
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--start", default="2026-09-16")
    parser.add_argument("--end", default="2026-10-15")
    parser.add_argument("--limit", type=int, help="Limit number of mountain stations for a bounded pilot")
    parser.add_argument("--workers", type=int, choices=(1,2), default=2)
    parser.add_argument("--timeout", type=int, choices=range(5,121), default=25, metavar="5..120")
    args = parser.parse_args()
    if args.command == "export":
        from weather_dataset import build
        build(args.output)
        return
    c = Collector(args.output,args.timeout)
    if args.command == "probe":
        c.probe()
    elif args.command == "history":
        c.history(args.start, args.end)
    elif args.command in ("latest", "refresh"):
        c.latest()
        if args.command == "refresh":
            from weather_dataset import build
            build(args.output)
    elif args.command == "mountain-history":
        c.mountain_history(args.start, args.end, args.limit, args.workers)
    elif args.command == "sounding-history":
        c.sounding_history(args.start, args.end)
    elif args.command == "radar":
        c.radar()
    elif args.command == "coordinates":
        c.fetch("radar_coordinates_netcdf", "/api/typ01/url/rdr_latlon_file_down.php", dict(cmp="PCP"))
    else:
        c.extended()


if __name__ == "__main__":
    main()
