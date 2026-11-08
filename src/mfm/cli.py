"""命令行入口。

用法：
  python -m mfm fetch baidu  --out data/baidu.json            # 打印待执行 JS
  python -m mfm fetch amap   --out data/amap.json
  python -m mfm convert --from baidu --input data/baidu.json --to amap --out data/import_amap.js
  python -m mfm convert --from amap  --input data/amap.json  --to baidu --out data/import_baidu.js
  python -m mfm redact --input data/baidu.json --out data/baidu_redacted.json
  python -m mfm export --input data/baidu.json --format csv --out data/baidu.csv
"""
import argparse
import json
import os
import sys

from . import amap, baidu, redact as rdt
from .baidu_write import build_import_script as build_baidu_import


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def cmd_fetch(args):
    if args.platform == "baidu":
        js = baidu.build_fetch_script()
        hint = "在已登录的 https://map.baidu.com 页面执行上面脚本，把返回值存成 JSON"
    else:
        js = amap.FETCH_SCRIPT
        hint = "在 https://ditu.amap.com/faves?innersrc=uriapi（已登录）页面执行上面脚本"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(js)
        print(f"脚本已写入 {args.out}\n{hint}")
    else:
        print(js)


def cmd_parse(args):
    raw = _read(args.input)
    if args.platform == "baidu":
        rows_raw, log = baidu.parse_fetch_result(raw)
        rows = baidu.to_normalized(rows_raw)
    else:
        rows, ver = amap.parse_fetch_result(raw)
    _write_json(rows, args.out)
    print(f"解析 {len(rows)} 条 -> {args.out}")


def cmd_convert(args):
    rows = _read(args.input)
    if args.to == "amap":
        js, n = amap.build_import_script(rows, batch=args.batch)
    else:
        js, n = build_baidu_import(rows, batch=args.batch)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"生成导入脚本 {n} 条 -> {args.out}")


def cmd_redact(args):
    rows = _read(args.input)
    out = [rdt.redact_row(r, precision=args.precision) for r in rows]
    leaks = rdt.scan_leaks(out)
    _write_json(out, args.out)
    print(f"脱敏 {len(out)} 条 -> {args.out}")
    if leaks:
        print(f"⚠️ 仍有 {len(leaks)} 条疑似未脱敏：{leaks[:5]}", file=sys.stderr)
    else:
        print("✓ 自检通过：无手机号/身份证残留")


def cmd_export(args):
    rows = _read(args.input)
    if args.format == "csv":
        import csv
        with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "address", "city", "lng", "lat"])
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in w.fieldnames})
    else:
        _write_json(rows, args.out)
    print(f"导出 {len(rows)} 条 -> {args.out}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mfm", description="百度/高德地图收藏双向迁移")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="生成抓取脚本")
    p.add_argument("platform", choices=["baidu", "amap"])
    p.add_argument("--out")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("parse", help="解析抓取结果")
    p.add_argument("platform", choices=["baidu", "amap"])
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("convert", help="生成导入脚本")
    p.add_argument("--from", dest="frm", required=True, choices=["baidu", "amap"])
    p.add_argument("--to", required=True, choices=["baidu", "amap"])
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--batch", type=int, default=50)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("redact", help="脱敏")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--precision", type=int, default=2)
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("export", help="导出 CSV/JSON")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--format", choices=["csv", "json"], default="csv")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
