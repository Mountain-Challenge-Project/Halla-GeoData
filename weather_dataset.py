"""Offline CSV normalization, coverage checks and local dataset inventory.

This module never calls a network service and never reads an API key.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from weather_collect import (ROOT, OUT, KST, parse_asos, parse_aws, data_lines,
                             save_json, write_csv, decode)

ASOS = {
    "temperature_c": ("TA", "degC", 1), "dewpoint_c": ("TD", "degC", 1),
    "relative_humidity_pct": ("HM", "%", 1), "station_pressure_hpa": ("PA", "hPa", 1),
    "sea_level_pressure_hpa": ("PS", "hPa", 1), "wind_speed_ms": ("WS", "m/s", 1),
    "wind_direction_deg": ("WD", "degree", 10), "rainfall_window_mm": ("RN", "mm", 1),
    "rainfall_day_mm": ("RN_DAY", "mm", 1), "rain_intensity_mmh": ("RN_INT", "mm/h", 1),
    "visibility_m": ("VS", "m", 10), "solar_radiation_mj_m2": ("SI", "MJ/m2", 1),
    "sunshine_hours": ("SS", "hour", 1), "snow_depth_cm": ("SD_TOT", "cm", 1),
}
AWS = {
    "temperature_c": ("TA", "degC", 1), "dewpoint_c": ("TD", "degC", 1),
    "relative_humidity_pct": ("HM", "%", 1), "station_pressure_hpa": ("PA", "hPa", 1),
    "sea_level_pressure_hpa": ("PS", "hPa", 1), "wind_speed_ms": ("WS10", "m/s", 1),
    "wind_direction_deg": ("WD10", "degree", 1), "gust_speed_ms": ("WSS", "m/s", 1),
    "rainfall_15min_mm": ("RN_15m", "mm", 1), "rainfall_60min_mm": ("RN_60m", "mm", 1),
    "rainfall_12h_mm": ("RN_12h", "mm", 1), "rainfall_day_mm": ("RN_DAY", "mm", 1),
}
UNITS_FCST = {"T1H":"degC", "TMP":"degC", "TMN":"degC", "TMX":"degC", "REH":"%", "UUU":"m/s", "VVV":"m/s", "WSD":"m/s", "VEC":"degree", "RN1":"mm per 1h (numeric or category)", "PCP":"mm per 1h (numeric or category)", "SNO":"cm per 1h (numeric or category)", "POP":"%", "WAV":"m", "SKY":"code", "PTY":"code", "LGT":"code"}


def numeric(raw, field, network):
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return "", "not_numeric"
    if not math.isfinite(value):
        return "", "nonfinite"
    if network == "AWS" and value <= -50:
        return "", "provider_missing_or_error"
    if network == "SFC":
        if field in ("TA", "TD"):
            if value <= -90:
                return "", "provider_missing_or_error"
        elif value < 0:
            return "", "negative_code_unresolved"
    if field in ("TA", "TD") and not -80 <= value <= 60:
        return "", "outside_screening_range"
    if field == "HM" and not 0 <= value <= 100:
        return "", "outside_screening_range"
    if field in ("PA", "PS") and not 500 <= value <= 1100:
        return "", "outside_screening_range"
    if field in ("WS", "WS10", "WSS") and not 0 <= value <= 150:
        return "", "outside_screening_range"
    if field.startswith("RN") and value < 0:
        return "", "negative_code_unresolved"
    if field == "WD" and not 0 <= value <= 36:
        return "", "outside_screening_range"
    if field == "WD10" and not 0 <= value <= 360:
        return "", "outside_screening_range"
    return value, "basic_checks_only"


def normalize(row, network, station=None):
    tm = datetime.strptime(row["TM"], "%Y%m%d%H%M").replace(tzinfo=KST)
    station = station or {}
    result = dict(observed_at_utc=tm.astimezone(timezone.utc).isoformat(), observed_at_kst=tm.isoformat(),
                  station_id=row["STN"], station_name=station.get("name", ""), network=network,
                  longitude=station.get("longitude", ""), latitude=station.get("latitude", ""),
                  ground_elevation_m=station.get("ground_elevation_m", ""))
    missing = []
    for name, (field, unit, scale) in (ASOS if network == "SFC" else AWS).items():
        value, qc = numeric(row[field], field, network)
        if field == "WD" and value == 0:
            value, qc = "", "calm_or_direction_code_zero"
        if field == "WD10" and value == 360:
            value, qc = "", "calm_direction_code"
        result[name] = round(value*scale, 6) if value != "" else ""
        if qc != "basic_checks_only":
            missing.append(field + ":" + qc)
    if network == "SFC":
        window = 60 if 4 <= tm.month <= 10 else 180
        result["rainfall_window_minutes"] = window
        result["rainfall_window_start_utc"] = (tm-timedelta(minutes=window)).astimezone(timezone.utc).isoformat()
        result["IR_raw"] = row["IR"]
    result["qc_flags"] = ";".join(missing) or "basic_checks_only"
    result["quality_note"] = "provider_raw_retained; no interpolation; no independent validation"
    return result


def parse_forecast(payload, received_at):
    response = json.loads(decode(payload))["response"]
    if str(response["header"]["resultCode"]) != "00":
        raise ValueError("Forecast API returned non-success resultCode")
    body = response["body"]
    items = body["items"]["item"]
    if len(items) != int(body["totalCount"]):
        raise ValueError("Forecast pagination incomplete")
    if not items:
        raise ValueError("Empty forecast")
    rows = []
    for item in items:
        issued = datetime.strptime(item["baseDate"]+item["baseTime"], "%Y%m%d%H%M").replace(tzinfo=KST)
        valid = datetime.strptime(item["fcstDate"]+item["fcstTime"], "%Y%m%d%H%M").replace(tzinfo=KST)
        rows.append(dict(issued_at_kst=issued.isoformat(), issued_at_utc=issued.astimezone(timezone.utc).isoformat(),
                         valid_at_kst=valid.isoformat(), valid_at_utc=valid.astimezone(timezone.utc).isoformat(),
                         available_at_utc="", received_at_utc=received_at,
                         nx=item["nx"], ny=item["ny"], category=item["category"], value_raw=item["fcstValue"],
                         unit=UNITS_FCST.get(item["category"], "unverified"),
                         lead_hours=(valid-issued).total_seconds()/3600,
                         quality_note="native forecast grid; no 500m downscaling"))
    keys = [(r["issued_at_utc"],r["valid_at_utc"],r["nx"],r["ny"],r["category"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate forecast keys")
    return rows


def parse_sounding(payload, station_id="47186"):
    if "#7777END" not in decode(payload):
        raise ValueError("Incomplete sounding response")
    rows = []
    for line in data_lines(payload):
        t = line.split()
        if len(t) != 9 or len(t[0]) != 12 or not t[0].isdigit():
            raise ValueError("Sounding schema mismatch")
        if t[1] != station_id:
            continue
        tm = datetime.strptime(t[0], "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        row = dict(observed_at_utc=tm.isoformat(), observed_at_kst=tm.astimezone(KST).isoformat(),
                   station_id=t[1], station_name="국가태풍센터", level_sequence=len(rows)+1)
        for field, raw in zip(("pressure_hpa", "height_m", "temperature_c", "dewpoint_c", "wind_direction_deg", "wind_speed_ms"), t[2:8]):
            row[field+"_raw"] = raw
            row[field] = "" if float(raw) <= -990 else float(raw)
        row["provider_flag"] = t[8]
        row["quality_note"] = "native levels; no vertical interpolation; terrain masking required before gridding"
        rows.append(row)
    return rows


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def build(output=OUT):
    output = Path(output)
    entries = [json.loads(line) for line in (output / "requests.jsonl").read_text("utf-8").splitlines()]
    by_path = {e["raw_path"].replace("\\", "/"):e for e in entries if e.get("raw_path")}
    validation = []
    inventory = []
    availability = []
    latest = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "sources": {}}
    stations = {inf:{r["station_id"]:r for r in read_csv(output / "csv" / ("stations_"+inf.lower()+".csv"))} for inf in ("SFC","AWS")}
    # Recover complete archived chunks even when a network interruption stopped
    # the collector before its per-station CSV was written.
    archived = defaultdict(dict)
    requested_days = set()
    chunk_errors = []
    for folder in sorted((output/"raw").glob("aws_minute_*")):
        match = re.fullmatch(r"aws_minute_(\d+)_(\d{8})(?:_h(\d{2}))?",folder.name)
        if not match:
            continue
        sid,day,hour = match.groups()
        requested_days.add(day)
        for path in reversed(sorted(folder.glob("*.txt"))):
            try:
                part = parse_aws(path.read_bytes())
                if any(r["STN"] != sid or r["TM"][:8] != day for r in part):
                    raise ValueError("Response station/date mismatch")
                for row in part:
                    archived[sid][row["TM"]] = row
                break
            except ValueError:
                chunk_errors.append(dict(raw_file=path.relative_to(output).as_posix(),status="incomplete_or_invalid_excluded"))
    if requested_days:
        first,last=min(requested_days),max(requested_days)
        for sid,values in archived.items():
            write_csv(output/"csv"/("aws_minute_"+sid+"_"+first+"_"+last+"_raw.csv"),[values[k] for k in sorted(values)])
    save_json(output/"quality"/"aws_chunk_validation.json",chunk_errors)

    def record_csv(path, rows, note, expected=None, time_field="observed_at_kst"):
        if not rows:
            validation.append(dict(dataset=path.relative_to(output).as_posix(), status="empty"))
            return
        write_csv(path, rows)
        times = [r[time_field] for r in rows if r.get(time_field)]
        inventory.append(dict(file=path.relative_to(output).as_posix(), rows=len(rows), expected_rows=expected if expected is not None else "",
                              stations=len({r["station_id"] for r in rows if r.get("station_id")}),
                              first_time=min(times) if times else "", last_time=max(times) if times else "",
                              note=note, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    def assess(rows, group, expected):
        by_station = defaultdict(list)
        for row in rows:
            by_station[row["station_id"]].append(row)
        for station_id, items in by_station.items():
            network = items[0]["network"]
            for variable in (ASOS if network == "SFC" else AWS):
                count = sum(r[variable] != "" for r in items)
                availability.append(dict(dataset=group, station_id=station_id, station_name=items[0]["station_name"],
                                         variable=variable, expected_records=expected, received_records=len(items),
                                         usable_after_basic_checks=count, missing_or_flagged=len(items)-count,
                                         usable_fraction_of_expected=round(count/expected,6) if expected else ""))

    for path in sorted((output / "csv").glob("asos_hourly_*_raw.csv")):
        raw = read_csv(path)
        rows = [normalize(r,"SFC",stations["SFC"].get(r["STN"])) for r in raw]
        dates = sorted({r["TM"][:8] for r in raw})
        days = (datetime.strptime(dates[-1],"%Y%m%d")-datetime.strptime(dates[0],"%Y%m%d")).days+1
        expected = days*24
        keys = [(r["station_id"],r["observed_at_kst"]) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate ASOS station/time")
        record_csv(path.with_name(path.name.replace("_raw.csv",".csv")), rows, "ASOS native hourly; negative rain codes remain missing", expected*len(stations["SFC"]))
        assess(rows, path.stem, expected)

    for path in sorted((output / "csv").glob("aws_minute_*_raw.csv")):
        raw = read_csv(path)
        # Skip pilot outputs if the complete interval for the same station exists.
        station_id = path.stem.split("_")[2]
        candidates = list((output / "csv").glob("aws_minute_"+station_id+"_*_raw.csv"))
        if path != max(candidates, key=lambda p:p.stat().st_size):
            continue
        rows = [normalize(r,"AWS",stations["AWS"].get(r["STN"])) for r in raw]
        tag = path.stem.split("_")
        days = (datetime.strptime(tag[4],"%Y%m%d")-datetime.strptime(tag[3],"%Y%m%d")).days+1
        keys = [(r["station_id"],r["observed_at_kst"]) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate AWS station/time")
        record_csv(path.with_name(path.name.replace("_raw.csv",".csv")), rows, "AWS native minute; 10-minute mean wind and rolling accumulation", days*1440)
        assess(rows,path.stem,days*1440)
        hourly = [r for r in rows if r["observed_at_kst"][14:16] == "00"]
        record_csv(path.with_name(path.name.replace("aws_minute_","aws_hourly_snapshot_").replace("_raw.csv",".csv")), hourly, "Exact top-of-hour sample, not hourly mean or interpolated series", days*24)

    for path in sorted((output / "csv").glob("aws_daily_*.csv")):
        rows = read_csv(path)
        record_csv(path,rows,"Five daily variables in long format; date uses KST", time_field="date_kst")
        parts = path.stem.split("_")
        first_day = datetime.strptime(parts[-2],"%Y%m%d")
        last_day = datetime.strptime(parts[-1],"%Y%m%d")
        days = [(first_day+timedelta(days=i)).date().isoformat() for i in range((last_day-first_day).days+1)]
        variables = ["rn_day","ta_max","ta_min","ws_max","ws_ins_max"]
        actual = {(r["station_id"],r["date_kst"],r["variable"]) for r in rows}
        gaps = [dict(station_id=stn,date_kst=d,variable=v,status="not_returned") for stn in stations["AWS"] for d in days for v in variables if (stn,d,v) not in actual]
        write_csv(output / "quality" / "daily_missing_records.csv", gaps, ["station_id","date_kst","variable","status"])

    for name, parser in (("asos_latest",parse_asos),("ultra_forecast",parse_forecast),("short_forecast",parse_forecast),("sounding_latest",parse_sounding)):
        files = sorted((output / "raw" / name).glob("*.txt"))
        for path in reversed(files):
            meta = by_path[path.relative_to(output).as_posix()]
            try:
                if "forecast" in name:
                    rows = parser(path.read_bytes(),meta["received_at_utc"])
                    moment = "issued_at_kst"
                else:
                    rows = parser(path.read_bytes())
                    if name == "asos_latest":
                        rows = [normalize(r,"SFC",stations["SFC"].get(r["STN"])) for r in rows]
                    moment = "observed_at_kst"
                if not rows:
                    raise ValueError("No selected-region observations")
                path_csv = output / "latest" / (name + ".csv")
                record_csv(path_csv,rows,"Latest successfully parsed snapshot; actual publication availability unknown",time_field=moment)
                last_attempt = next(e for e in reversed(entries) if e["dataset"]==name)
                latest["sources"][name] = dict(csv=path_csv.relative_to(output).as_posix(), rows=len(rows), source_time_kst=max(r[moment] for r in rows),
                                              received_at_utc=meta["received_at_utc"], last_attempt_status=last_attempt["status"],
                                              using_older_success=last_attempt.get("raw_path")!=meta["raw_path"],
                                              stale_after_seconds=5400 if name=="asos_latest" else 14400 if name=="short_forecast" else 21600 if name=="sounding_latest" else 7200)
                break
            except (ValueError,KeyError,TypeError) as exc:
                validation.append(dict(dataset=name,raw_file=path.relative_to(output).as_posix(),status="parse_failed",reason=str(exc)))

    aws_latest = {}
    aws_candidates = list((output / "raw" / "aws_minute_latest").glob("*.txt"))
    aws_candidates += [p for folder in (output/"raw").glob("aws_latest_*") for p in folder.glob("*.txt")]
    aws_candidates += list((output/"raw"/"aws_summit_probe").glob("*.txt"))
    for path in sorted(aws_candidates,key=lambda p:p.name):
        try:
            for r in parse_aws(path.read_bytes()):
                if r["STN"] in stations["AWS"] and (r["STN"] not in aws_latest or r["TM"] >= aws_latest[r["STN"]][0]["TM"]):
                    aws_latest[r["STN"]] = (r,by_path[path.relative_to(output).as_posix()])
        except ValueError as exc:
            validation.append(dict(dataset="aws_latest",status="parse_failed",reason=str(exc)))
    if aws_latest:
        rows = []
        for raw, meta in aws_latest.values():
            r = normalize(raw,"AWS",stations["AWS"][raw["STN"]])
            r["received_at_utc"] = meta["received_at_utc"]
            rows.append(r)
        record_csv(output/"latest"/"aws_latest.csv",rows,"Per-station latest success; station times may differ",len(stations["AWS"]))
        latest["sources"]["aws_latest"] = dict(csv="latest/aws_latest.csv",rows=len(rows),expected_stations=len(stations["AWS"]),
                                               source_time_kst_min=min(r["observed_at_kst"] for r in rows), source_time_kst=max(r["observed_at_kst"] for r in rows),
                                               received_at_utc=max(r["received_at_utc"] for r in rows),stale_after_seconds=3600,
                                               note="Read individual row timestamps; missing stations are not zero values")
        assess(rows,"latest_aws",1)

    soundings = []
    profile_counts = []
    for folder in sorted((output/"raw").glob("sounding_47186_*")):
        files = sorted(folder.glob("*.txt"))
        if not files:
            continue
        try:
            rows = parse_sounding(files[-1].read_bytes())
            expected=datetime.strptime(folder.name[-12:],"%Y%m%d%H%M").replace(tzinfo=timezone.utc).isoformat()
            if any(r["observed_at_utc"] != expected for r in rows):
                raise ValueError("Sounding timestamp differs from request")
            soundings.extend(rows)
            profile_counts.append(dict(requested_time_utc=folder.name[-12:],levels=len(rows),status="parsed" if rows else "empty"))
        except ValueError as exc:
            profile_counts.append(dict(requested_time_utc=folder.name[-12:],levels=0,status="parse_failed"))
    record_csv(output/"csv"/"sounding_47186_history.csv",soundings,"Native vertical levels; -999 retained in raw fields; no surface extrapolation")
    profile_index={p["requested_time_utc"]:p for p in profile_counts}
    for entry in entries:
        if entry["dataset"].startswith("sounding_47186_"):
            tag=entry["dataset"][-12:]
            if tag not in profile_index:
                profile_index[tag]=dict(requested_time_utc=tag,levels=0,status="not_received")
    write_csv(output/"quality"/"sounding_profiles.csv",[profile_index[k] for k in sorted(profile_index)],["requested_time_utc","levels","status"])
    write_csv(output/"quality"/"station_variable_availability.csv",availability)
    # Explicitly list unreceived mountain station-period combinations as well.
    if requested_days:
        expected_days=(datetime.strptime(max(requested_days),"%Y%m%d")-datetime.strptime(min(requested_days),"%Y%m%d")).days+1
        coverage=[]
        for sid,station in stations["AWS"].items():
            if float(station["ground_elevation_m"]) < 700:
                continue
            received=len(archived.get(sid,{}))
            coverage.append(dict(station_id=sid,station_name=station["name"],expected_minutes=expected_days*1440,
                                 received_complete_response_minutes=received,missing_minutes=expected_days*1440-received,
                                 completeness_fraction=round(received/(expected_days*1440),6)))
        write_csv(output/"quality"/"mountain_history_coverage.csv",coverage)
    radar_csv=output/"csv"/"radar_jeju_native_points.csv"
    if radar_csv.exists():
        record_csv(radar_csv,read_csv(radar_csv),"Official PCP native grid points in Jeju bbox, including sea; negative codes unresolved",time_field="window_end_kst")
    write_csv(output/"file_inventory.csv",inventory)
    save_json(output/"quality"/"parse_validation.json",validation)
    # Publish immutable files first, then atomically move the manifest pointer.
    version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for name, state in latest["sources"].items():
        source = output/state["csv"]
        destination = output/"snapshots"/version/(name+".csv")
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        state["csv"] = destination.relative_to(output).as_posix()
        tm = datetime.fromisoformat(state["source_time_kst"])
        state["age_seconds_at_publish"] = round((datetime.now(timezone.utc)-tm).total_seconds())
        state["stale_at_publish"] = state["age_seconds_at_publish"] > state["stale_after_seconds"] or state.get("using_older_success",False)
        state["status"] = "stale" if state["stale_at_publish"] else "available"
        if name == "aws_latest":
            state["missing_station_ids"] = sorted(set(stations["AWS"])-set(aws_latest))
    save_json(output/"latest"/"latest.json",latest)

    api = defaultdict(list)
    for entry in entries:
        api[entry["endpoint"]].append(entry)
    api_rows = []
    for endpoint, attempts in api.items():
        good = [e for e in attempts if e["status"]=="downloaded_unvalidated"]
        api_rows.append(dict(endpoint=endpoint, request_count=len(attempts), downloaded_responses=len(good),
                             last_http_status=attempts[-1]["http_status"], last_transport_status=attempts[-1]["status"],
                             last_success_received_utc=good[-1]["received_at_utc"] if good else "",
                             parameters_json=json.dumps(attempts[-1]["parameters"],ensure_ascii=False),
                             note="HTTP success is separate from parse success and meteorological quality"))
    write_csv(output/"api_status.csv",api_rows)
    save_json(output/"collection_summary.json",dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),
              files=inventory, api=api_rows, parse_failures=validation,excluded_aws_responses=chunk_errors,
              unique_aws_metadata_stations=len(stations["AWS"]),unique_asos_metadata_stations=len(stations["SFC"])))
    print(json.dumps(dict(output=str(output),csv_datasets=len(inventory),parse_failures=len(validation)),ensure_ascii=False))
    return inventory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUT)
    build(parser.parse_args().output)
