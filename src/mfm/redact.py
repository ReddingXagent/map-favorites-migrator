"""脱敏：导出/开源前清除个人可识别信息。

规则：
- 坐标降精度到 ~1km（保留 2 位小数）
- 名称/地址里的门牌号、房间号、手机号、身份证号打码
- 可选的「地名白名单」模式：只保留通用地理名，其余替换成「某地」
"""
import re

# 中国大陆手机号
PHONE_RE = re.compile(r"1[3-9]\d{9}")
# 固话
TEL_RE = re.compile(r"0\d{2,3}-?\d{7,8}")
# 身份证
ID_RE = re.compile(r"\d{17}[\dXx]|\d{15}")
# 门牌号：数字+号 / 数字+室 / 数字+栋 / 数字+层 / 数字+单元
ADDR_NUM_RE = re.compile(
    r"\d+\s*(?:号|室|栋|幢|层|楼|单元|弄|巷|门|座|区|期|栋|号楼|室)\S{0,6}"
)
# 邮编
ZIP_RE = re.compile(r"\b\d{6}\b")


def redact_text(s, keep_numbers=False):
    """清理文本里的敏感片段。"""
    if not s:
        return ""
    # 先处理长串（身份证 18 位）再处理手机号，否则身份证会被手机号正则截断
    s = ID_RE.sub("<ID>", s)
    s = PHONE_RE.sub("<PHONE>", s)
    s = TEL_RE.sub("<TEL>", s)
    if not keep_numbers:
        s = ADDR_NUM_RE.sub("<NUM>", s)
        s = ZIP_RE.sub("<ZIP>", s)
    return s.strip()


def redact_coord(lng, lat, precision=2):
    """坐标降精度。precision=2 约 1km，3 约 100m。"""
    return round(float(lng), precision), round(float(lat), precision)


def redact_row(row, precision=2):
    """对一条收藏记录脱敏。"""
    out = dict(row)
    out["name"] = redact_text(row.get("name", ""))
    out["address"] = redact_text(row.get("address") or row.get("addr") or "")
    if row.get("lng") is not None and row.get("lat") is not None:
        out["lng"], out["lat"] = redact_coord(row["lng"], row["lat"], precision)
    for k in ("phone", "tel", "uid", "user_id"):
        if k in out:
            out[k] = "<REDACTED>"
    # 精确墨卡托坐标也降精度（保留到 ~1km）
    for k in ("bd_x", "bd_y"):
        if out.get(k) not in (None, ""):
            try:
                step = 1000 if precision == 2 else (100 if precision == 3 else 1)
                out[k] = int(round(float(out[k]) / step) * step)
            except (TypeError, ValueError):
                out[k] = "<REDACTED>"
    # sid / poiid 是内部 id，隐藏
    for k in ("sid", "poiid"):
        if k in out:
            out[k] = "<REDACTED>"
    return out


# 自检只看文本字段，不扫数值字段（坐标/墨卡托值本身是长串数字，会误报）
TEXT_FIELDS = ("name", "address", "city", "custom_name", "custom_address")


def scan_leaks(rows):
    """自检：返回疑似未脱敏的条目。只检查文本字段。"""
    hits = []
    for i, r in enumerate(rows):
        blob = " ".join(str(r.get(k, "")) for k in TEXT_FIELDS)
        if PHONE_RE.search(blob) or ID_RE.search(blob) or TEL_RE.search(blob):
            hits.append((i, r.get("name", "")))
    return hits
