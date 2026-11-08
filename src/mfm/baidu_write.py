"""百度收藏写入（反向：高德 -> 百度）。

百度收藏有写接口 `qt=fav&mode=set&type=favdata`（提交完整列表同步）。
结构：{ sid, ver, action:'add', detail:{ data:{ extdata:{ name, geoptx, geopty }, sourcedata:{ address, address_detail } } } }

注意：百度侧对批量写入更严格，建议控制在 100 条/批，并在每批后读回核对。
"""
import hashlib
import json
import time


def _sid(name, x, y):
    """稳定的 sid，保证重复导入幂等。"""
    h = hashlib.md5(f"{name}|{int(float(x))}|{int(float(y))}".encode()).hexdigest()
    return f"11_{h}"


def to_baidu_record(row, ts=None):
    """标准化记录 -> 百度收藏记录。"""
    from .coords import gcj_to_bd_mc

    ts = ts or int(time.time())
    lng, lat = float(row["lng"]), float(row["lat"])
    x, y = gcj_to_bd_mc(lng, lat)
    x, y = int(round(x)), int(round(y))
    name = (row.get("name") or "").strip()
    addr = (row.get("address") or "").strip()
    sid = row.get("id") if (row.get("from_baidu") and row.get("id")) else _sid(name, x, y)
    return {
        "sid": sid,
        "cid": sid,
        "ver": str(ts),
        "action": "add",
        "status": "100",
        "detail": {
            "data": {
                "type": "11",
                "fid": sid,
                "mtime": str(ts),
                "ctime": str(ts),
                "topTime": "0",
                "extdata": {
                    "name": name,
                    "poitype": 3,
                    "geoptx": x,
                    "geopty": y,
                    "uid": "",
                    "content": "",
                    "version": 0,
                    "poistyle": 0,
                },
                "sourcedata": {
                    "address": addr,
                    "address_detail": {"city": row.get("city", "")},
                },
            }
        },
    }


FETCH_SCRIPT = r"""(async function () {
  var base = 'https://map.baidu.com/?newmap=1&reqflag=pcmap&biz=1&from=webmap&da_par=direct&pcevaname=pc4.1&qt=fav&mode=get&type=favdata&limit=100&newfrom=zhuzhan_webmap';
  var all = [], seen = new Set(), lastver = 0, round = 0;
  while (round++ < 60) {
    var r = await fetch(base + '&lastver=' + lastver + '&t=' + Date.now(), { credentials: 'include' });
    var j = await r.json(), s = j.sync || {}, nd = s.newdata || [];
    if (!nd.length) break;
    var fresh = 0;
    nd.forEach(function (x) {
      if (!seen.has(x.sid + '|' + x.ver)) { seen.add(x.sid + '|' + x.ver); all.push(x); fresh++; }
    });
    if (!fresh || !s.lastver) break;
    lastver = s.lastver;
    await new Promise(function (res) { setTimeout(res, 200); });
  }
  var best = {};
  all.forEach(function (x) {
    var v = parseInt(x.ver || '0', 10);
    if (!best[x.sid] || v > parseInt(best[x.sid].ver || '0', 10)) best[x.sid] = x;
  });
  return JSON.stringify({
    existing: Object.keys(best).map(function (k) { return best[k]; })
      .filter(function (x) { return x.action !== 'del'; })
      .map(function (x) { return x.sid; })
  });
})()"""


IMPORT_TEMPLATE = r"""(async function () {
  const RECORDS = __RECORDS__;
  const BATCH = __BATCH__;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const BASE = 'https://map.baidu.com/?newmap=1&reqflag=pcmap&biz=1&from=webmap&da_par=direct&pcevaname=pc4.1&qt=fav&mode=set&type=favdata&newfrom=zhuzhan_webmap';

  // 读现有（拿 sid 集合，避免重复写）
  const cur = await (await fetch('https://map.baidu.com/?newmap=1&reqflag=pcmap&biz=1&from=webmap&da_par=direct&pcevaname=pc4.1&qt=fav&mode=get&type=favdata&limit=100&lastver=0&newfrom=zhuzhan_webmap', { credentials: 'include' })).json();
  const have = new Set(((cur.sync && cur.sync.newdata) || []).map(x => x.sid));
  const pending = RECORDS.filter(r => !have.has(r.sid));
  const log = ['existing=' + have.size + ' pending=' + pending.length];
  if (!pending.length) return JSON.stringify({ ok: true, added: 0, log: log });

  for (let i = 0; i < pending.length; i += BATCH) {
    const chunk = pending.slice(i, i + BATCH);
    const body = new URLSearchParams();
    body.set('data', JSON.stringify(chunk));
    const r = await fetch(BASE + '&t=' + Date.now(), {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString()
    });
    const txt = await r.text();
    log.push('batch ' + (i / BATCH + 1) + ' http=' + r.status + ' resp=' + txt.slice(0, 120));
    await sleep(2500);
  }
  return JSON.stringify({ ok: true, pending: pending.length, log: log });
})()"""


def build_import_script(rows, batch=100):
    records = [to_baidu_record(r) for r in rows if r.get("name") and r.get("lng") and r.get("lat")]
    js = IMPORT_TEMPLATE.replace("__RECORDS__", json.dumps(records, ensure_ascii=False)).replace("__BATCH__", str(batch))
    return js, len(records)
