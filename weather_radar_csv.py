"""Optional offline PCPH point export. Run with QGIS Python (GDAL + NumPy)."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import numpy as np
from osgeo import gdal
from weather_collect import OUT, data_lines, save_json, write_csv, KST
from kma_client import inspect_ascii


def main():
    gdal.UseExceptions()
    coord_files = sorted((OUT/"raw"/"radar_coordinates_netcdf").glob("*.txt"))
    radar_files = sorted((OUT/"raw"/"radar_latest").glob("*.txt"))
    if not coord_files or not radar_files:
        raise SystemExit("Download PCP coordinates and PCPH radar first")
    coordinate_path, radar_path = coord_files[-1], radar_files[-1]
    dataset = gdal.Open(str(coordinate_path))
    subdatasets = dataset.GetSubDatasets()
    arrays = {}
    for name, description in subdatasets:
        if name.endswith("//lat") or name.endswith("//lon"):
            arrays[name.rsplit("//",1)[1]] = gdal.Open(name).ReadAsArray()
    lat, lon = arrays["lat"], arrays["lon"]
    payload = radar_path.read_bytes()
    validation = inspect_ascii(payload)
    shape = (validation["ny"],validation["nx"])
    if lat.shape != shape or lon.shape != shape:
        raise ValueError("Official coordinate dimensions do not match radar")
    lines = data_lines(payload)
    values = np.fromiter((int(v.strip()) for line in lines[1:] for v in line.rstrip("=").split(",") if v.strip()),dtype=np.int32,count=shape[0]*shape[1]).reshape(shape)
    mid = shape[1]//2
    south_to_north = bool(lat[0,mid] < lat[-1,mid])
    west_to_east = bool(lon[shape[0]//2,0] < lon[shape[0]//2,-1])
    if not south_to_north or not west_to_east:
        raise ValueError("Coordinate orientation requires separate verification")
    selected = np.isfinite(lat)&np.isfinite(lon)&(lat>=33.0)&(lat<=34.1)&(lon>=125.8)&(lon<=127.1)
    y,x = np.where(selected)
    log = [json.loads(s) for s in (OUT/"requests.jsonl").read_text("utf-8").splitlines()]
    record = next(e for e in reversed(log) if e.get("raw_path", "").replace("\\", "/")==radar_path.relative_to(OUT).as_posix())
    params = record["parameters"]
    if params.get("cmp") != "PCPH" or params.get("unit") != "MM":
        raise ValueError("Only explicit PCPH/MM supported")
    observed = datetime.strptime(params["tm"],"%Y%m%d%H%M").replace(tzinfo=KST)
    start = observed-timedelta(minutes=int(params["acc"]))
    def rows():
        for yy,xx in zip(y,x):
            encoded = int(values[yy,xx])
            yield dict(native_column_zero_based=int(xx),native_row_zero_based=int(yy),
                       longitude=round(float(lon[yy,xx]),7),latitude=round(float(lat[yy,xx]),7),
                       encoded_value=encoded,accumulation_mm=encoded*0.01 if encoded>=0 else "",
                       negative_code=encoded if encoded<0 else "",qc="negative_code_unresolved" if encoded<0 else "unvalidated_radar_estimate",
                       window_start_kst=start.isoformat(),window_end_kst=observed.isoformat(),
                       window_end_utc=observed.astimezone(timezone.utc).isoformat(),accumulation_minutes=int(params["acc"]),
                       product="PCPH",quality_product=params["qcd"],coordinate_source="KMA PCP NetCDF")
    target = OUT/"csv"/"radar_jeju_native_points.csv"
    write_csv(target,rows())
    save_json(OUT/"radar_coordinate_validation.json",dict(shape=shape,grid_metadata=dataset.GetMetadata(),
                coordinate_rows_south_to_north=south_to_north,coordinate_columns_west_to_east=west_to_east,
                bbox=[125.8,33.0,127.1,34.1],selected_points=len(x),
                orientation_check="passed",independent_control_points_checked=False,
                existing_500m_grid_alignment_verified=False,nodata_semantics_verified=False,
                output=target.relative_to(OUT).as_posix(),note="Official PCP coordinates paired to PCPH by matching dimensions and documented storage order; includes sea cells, no local-grid resampling"))
    print(json.dumps(dict(points=len(x),nonnegative_points=int((values[selected]>=0).sum()),shape=shape)))


if __name__ == "__main__":
    main()
