"""坐标系转换：百度 BD09MC / BD09 / GCJ02 / WGS84 互转。

百度收藏接口的 geoptx/geopty 是 BD09 墨卡托坐标（整数）。
反解成经纬度后，量级上直接对齐 GCJ02，不要再叠加 BD09→GCJ02 偏移。

校准依据：用 6 个高德已知 POI 反解比对，误差 <25m。
"""
import math

# 百度墨卡托反解的等效地球半径（经度方向）
RX = 6378551.0
# 纬度方向的等效半径随纬度线性变化（拟合实测数据）
A_LAT = 171.2338881546564
B_LAT = 6335150.130210205

X_PI = math.pi * 3000.0 / 180.0


def bd_mc_to_gcj(x, y):
    """百度墨卡托 -> GCJ02 经纬度 (lng, lat)。"""
    x = float(x)
    y = float(y)
    lat = y / 111320.0
    for _ in range(80):
        rp = A_LAT * lat + B_LAT
        nl = math.degrees(2 * math.atan(math.exp(y / rp)) - math.pi / 2)
        if abs(nl - lat) < 1e-11:
            lat = nl
            break
        lat = nl
    return math.degrees(x / RX), lat


def gcj_to_bd_mc(lng, lat):
    """GCJ02 -> 百度墨卡托 (x, y)，用于写回百度侧。"""
    lat = float(lat)
    rp = A_LAT * lat + B_LAT
    y = rp * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    x = math.radians(float(lng)) * RX
    return x, y


def bd09_to_gcj02(lng, lat):
    x = lng - 0.0065
    y = lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    t = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.cos(t), z * math.sin(t)


def gcj02_to_bd09(lng, lat):
    z = math.sqrt(lng * lng + lat * lat) + 0.00002 * math.sin(lat * X_PI)
    t = math.atan2(lat, lng) + 0.000003 * math.cos(lng * X_PI)
    return z * math.cos(t) + 0.0065, z * math.sin(t) + 0.006


def gcj02_to_amap_pixel(lng, lat):
    """GCJ02 -> 高德 zoom-20 像素坐标 (point_x, point_y)。"""
    R = 6378137.0
    circ = 2 * math.pi * R
    lat_r = max(min(lat, 85.0511287798), -85.0511287798) * math.pi / 180
    mx = R * max(min(lng, 180), -180) * math.pi / 180
    my = math.log((1 + math.sin(lat_r)) / (1 - math.sin(lat_r))) * R / 2
    size = 256 << 20
    mpp = circ / size
    x = (circ / 2 + mx) / mpp + 0.5
    y = circ / 2 - my
    return int(min(max(x, 0), size - 1)), int(min(max(int(y) / mpp + 0.5, 0), size - 1))


def amap_pixel_to_gcj(px, py):
    """高德 zoom-20 像素坐标 -> GCJ02 经纬度。"""
    R = 6378137.0
    circ = 2 * math.pi * R
    size = 256 << 20
    mpp = circ / size
    mx = (float(px) - 0.5) * mpp - circ / 2
    my = circ / 2 - (float(py) - 0.5) * mpp
    lng = math.degrees(mx / R)
    lat = math.degrees(2 * math.atan(math.exp(my / R)) - math.pi / 2)
    return lng, lat


def haversine(lng1, lat1, lng2, lat2):
    """两点球面距离（米）。"""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
