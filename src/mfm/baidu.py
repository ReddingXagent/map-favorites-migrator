"""百度地图收藏：抓取与转换。

百度收藏走增量同步接口 `qt=fav&mode=get&type=favdata`：
- 同一 sid 会出现多条记录（add / modify / del），必须按 ver 取最新、剔除 del
- `sync.newnum` 是服务端剩余条数，归零才算拉完
"""
import json
import os
import time


def build_fetch_script(page_size=100, max_rounds=60):
    """生成在 map.baidu.com 页面执行、返回全部收藏的 JS。"""
    return r"""(async function () {
  var base = 'https://map.baidu.com/?newmap=1&reqflag=pcmap&biz=1&from=webmap&da_par=direct&pcevaname=pc4.1&qt=fav&mode=get&type=favdata&limit=%(size)d&newfrom=zhuzhan_webmap';
  var all = [], seen = new Set(), lastver = 0, round = 0, log = [];
  while (round++ < %(rounds)d) {
    var r = await fetch(base + '&lastver=' + lastver + '&t=' + Date.now(), { credentials: 'include' });
    var j = await r.json(), s = j.sync || {}, nd = s.newdata || [];
    if (!nd.length) { log.push({ round: round, stop: 'empty' }); break; }
    var fresh = 0;
    nd.forEach(function (x) {
      if (!seen.has(x.sid + '|' + x.ver)) { seen.add(x.sid + '|' + x.ver); all.push(x); fresh++; }
    });
    log.push({ round: round, got: nd.length, fresh: fresh, newnum: s.newnum });
    if (!fresh || !s.lastver) break;
    lastver = s.lastver;
    await new Promise(function (res) { setTimeout(res, 200); });
  }
  var best = {};
  all.forEach(function (x) {
    var v = parseInt(x.ver || '0', 10);
    if (!best[x.sid] || v > parseInt(best[x.sid].ver || '0', 10)) best[x.sid] = x;
  });
  var rows = Object.keys(best).map(function (k) { return best[k]; })
    .filter(function (x) { return x.action !== 'del'; })
    .map(function (x) {
      var d = (x.detail || {}).data || {}, ed = d.extdata || {}, sd = d.sourcedata || {};
      return {
        sid: x.sid,
        name: ed.name || sd.name || '',
        address: sd.address || '',
        x: ed.geoptx,
        y: ed.geopty,
        city: (sd.address_detail || {}).city || ''
      };
    })
    .filter(function (r) { return r.name && r.x && r.y; });
  return JSON.stringify({ total: rows.length, rows: rows, log: log });
})()""" % {"size": page_size, "rounds": max_rounds}


def parse_fetch_result(raw_json_text):
    """解析上面脚本的返回值。"""
    data = json.loads(raw_json_text) if isinstance(raw_json_text, str) else raw_json_text
    return data.get("rows", []), data.get("log", [])


def to_normalized(rows):
    """百度原始行 -> 标准化记录（GCJ02）。"""
    from .coords import bd_mc_to_gcj

    out = []
    for r in rows:
        if not r.get("x") or not r.get("y"):
            continue
        lng, lat = bd_mc_to_gcj(r["x"], r["y"])
        out.append({
            "source": "baidu",
            "id": r.get("sid") or "",
            "name": (r.get("name") or "").strip(),
            "address": (r.get("address") or "").strip(),
            "city": (r.get("city") or "").strip(),
            "lng": round(lng, 6),
            "lat": round(lat, 6),
            "bd_x": r["x"],
            "bd_y": r["y"],
        })
    return out


def save_normalized(rows, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return path
