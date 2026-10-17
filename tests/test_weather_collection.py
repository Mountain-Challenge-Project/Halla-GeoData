import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import tempfile
from urllib.error import URLError
from datetime import datetime, timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from weather_collect import Collector, parse_aws, parse_asos, ASOS_FIELDS, KST
from weather_dataset import normalize, numeric, parse_forecast, parse_sounding


class WeatherContractTests(unittest.TestCase):
    def test_aws_requires_complete_terminator(self):
        line = "202609160000,871,10,1,10,2,20,1,10,0,0,0,0,0,50,840,1010,0,="
        with self.assertRaises(ValueError):
            parse_aws(line.encode())
        self.assertEqual(len(parse_aws((line+"\n#7777END").encode())),1)

    def test_aws_negative_celsius_is_valid_and_missing_is_blank(self):
        self.assertEqual(numeric("-9.0","TA","AWS")[0],-9)
        self.assertEqual(numeric("-99.9","TA","AWS")[0],"")
        self.assertEqual(numeric("-99.9","PA","AWS")[0],"")
        self.assertEqual(numeric("0","RN_60m","AWS")[0],0)

    def test_asos_rain_code_is_not_zero(self):
        self.assertEqual(numeric("-9.0","RN","SFC")[0],"")
        self.assertEqual(numeric("-9.0","TA","SFC")[0],-9)

    def test_kst_utc_and_wind_scaling(self):
        row = {field:"1" for field in ASOS_FIELDS}
        row.update(TM="202609160000",STN="184",WD="18",PA="1000",PS="1010",HM="50")
        clean = normalize(row,"SFC")
        self.assertEqual(clean["observed_at_utc"],"2026-09-15T15:00:00+00:00")
        self.assertEqual(clean["wind_direction_deg"],180)
        self.assertEqual(clean["rainfall_window_minutes"],60)
        row["TM"]="202612160000"
        self.assertEqual(normalize(row,"SFC")["rainfall_window_minutes"],180)

    def test_schema_error_does_not_shift_columns(self):
        with self.assertRaises(ValueError):
            parse_asos(b"202609160000 184 1 2")

    def forecast(self,total=1,code="00"):
        return json.dumps({"response":{"header":{"resultCode":code},"body":{"totalCount":total,"items":{"item":[{
            "baseDate":"20261015","baseTime":"2300","fcstDate":"20261016","fcstTime":"0100",
            "category":"PCP","fcstValue":"1.0mm 미만","nx":54,"ny":36}]}}}},ensure_ascii=False).encode()

    def test_forecast_keeps_categories_and_issue_valid_times(self):
        row = parse_forecast(self.forecast(),"2026-10-15T15:30:00+00:00")[0]
        self.assertEqual(row["value_raw"],"1.0mm 미만")
        self.assertEqual(row["lead_hours"],2)
        self.assertEqual(row["available_at_utc"],"")

    def test_forecast_incomplete_pages_and_service_error_fail(self):
        with self.assertRaises(ValueError):
            parse_forecast(self.forecast(total=2),"")
        with self.assertRaises(ValueError):
            parse_forecast(self.forecast(code="03"),"")

    def test_sounding_missing_and_negative_temperature(self):
        row = parse_sounding(b"202610150000 47186 500 5700 -12 -999 180 10 010000001000\n#7777END")[0]
        self.assertEqual(row["temperature_c"],-12)
        self.assertEqual(row["dewpoint_c"],"")
        self.assertEqual(row["dewpoint_c_raw"],"-999")

    def test_network_failure_stops_after_three_and_does_not_log_key(self):
        class Fail:
            calls=0
            def open(self,*args,**kwargs):
                self.calls+=1
                raise URLError(OSError(10013,"blocked"))
        with tempfile.TemporaryDirectory() as temp, patch("weather_collect.Config.load",return_value=SimpleNamespace(key="secret+value")):
            client=Collector(Path(temp))
            client.opener=Fail()
            with patch("builtins.print"):
                for i in range(4):
                    client.fetch("test", "/test",{})
            self.assertEqual(client.opener.calls,3)
            self.assertEqual(client.log[-1]["status"],"skipped_network_circuit_open")
            self.assertNotIn("secret",(Path(temp)/"requests.jsonl").read_text())

    def test_url_encoded_credential_echo_is_not_saved(self):
        class Response:
            status=200
            headers={}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return b"authKey=YOUR_TEST_secret%2Bvalue"
        class Echo:
            def open(self,*args,**kwargs): return Response()
        with tempfile.TemporaryDirectory() as temp, patch("weather_collect.Config.load",return_value=SimpleNamespace(key="YOUR_TEST_secret+value")):
            client=Collector(Path(temp))
            client.opener=Echo()
            with patch("builtins.print"):
                client.fetch("test","/test",{})
            self.assertEqual(client.log[-1]["status"],"credential_echo_blocked")
            self.assertFalse((Path(temp)/"raw").exists())

    def test_invalid_small_cached_chunk_is_retried(self):
        with patch("weather_collect.Config.load",return_value=SimpleNamespace(key="test")):
            client=Collector()
            client.cached_payload=lambda name:b"incomplete"
            valid=b"202609160000,871,10,1,10,2,20,1,10,0,0,0,0,0,50,840,1010,0,=\n#7777END"
            def fetch(*args):
                client.log.append({"http_status":200})
                return valid
            client.fetch=fetch
            start=datetime(2026,9,16,tzinfo=KST)
            with patch("weather_collect.time.sleep"):
                result=client.aws_period("test",start,start+timedelta(hours=1),"871")
            self.assertEqual(len(result),1)


if __name__ == "__main__":
    unittest.main()
