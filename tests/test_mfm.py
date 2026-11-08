"""坐标转换与脱敏的回归测试（不联网）。"""
import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mfm.coords import (  # noqa: E402
    bd_mc_to_gcj, gcj_to_bd_mc, gcj02_to_amap_pixel, amap_pixel_to_gcj, haversine,
)
from mfm.redact import redact_text, redact_coord, redact_row, scan_leaks  # noqa: E402

# 校准基准：百度墨卡托 -> 高德实际 GCJ02 坐标（6 个真实 POI）
CALIBRATION = [
    ((13523758, 3641872), (121.478183, 31.236250)),   # 春申江大厦
    ((12705293, 2560816), (114.125994, 22.540905)),   # 皇室假期美食水疗会
    ((12694903, 2582476), (114.032630, 22.721661)),   # 观兴东路
    ((13282661, 2989999), (119.312427, 26.073709)),   # 先施大厦
    ((13380944, 3512036), (120.195188, 30.228940)),   # 中国石化浙江石油
    ((12540850, 2547869), (112.648649, 22.433124)),   # 海鸿电气
]


def test_baidu_mercator_accuracy():
    for (x, y), (elng, elat) in CALIBRATION:
        lng, lat = bd_mc_to_gcj(x, y)
        err = haversine(lng, lat, elng, elat)
        assert err < 60, f"({x},{y}) 误差 {err:.0f}m 超出阈值"


def test_baidu_roundtrip():
    for (x, y), _ in CALIBRATION:
        lng, lat = bd_mc_to_gcj(x, y)
        x2, y2 = gcj_to_bd_mc(lng, lat)
        assert abs(x2 - x) < 5 and abs(y2 - y) < 5, f"往返偏差 ({abs(x2-x):.0f},{abs(y2-y):.0f})"


def test_amap_pixel_roundtrip():
    for _, (lng, lat) in CALIBRATION:
        px, py = gcj02_to_amap_pixel(lng, lat)
        l2, a2 = amap_pixel_to_gcj(px, py)
        assert haversine(lng, lat, l2, a2) < 2, "像素往返误差超 2m"


def test_amap_pixel_range():
    px, py = gcj02_to_amap_pixel(121.478, 31.236)
    assert 0 <= px < (256 << 20) and 0 <= py < (256 << 20)


def test_redact_phone():
    assert redact_text("联系13812345678") == "联系<PHONE>"


def test_redact_id():
    out = redact_text("身份证440301199001011234")
    assert "<ID>" in out


def test_redact_address_number():
    out = redact_text("浙江省杭州市西湖区文三路100号1506室")
    assert "100号" not in out and "1506室" not in out


def test_redact_coord_precision():
    assert redact_coord(121.478183, 31.236250, 2) == (121.48, 31.24)


def test_redact_row_no_leak():
    row = {"name": "某某公司", "address": "某某路1号", "lng": 121.478183, "lat": 31.23625,
           "phone": "13812345678"}
    out = redact_row(row)
    assert out["phone"] == "<REDACTED>"
    assert "1号" not in out["address"]
    assert scan_leaks([out]) == []


def test_scan_leaks_detects_phone():
    bad = {"name": "测试甲13812345678", "address": "", "city": ""}
    assert scan_leaks([bad]) != []
