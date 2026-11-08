"""高德地图收藏：抓取与写入脚本生成。

旧版 PC 页面（ditu.amap.com/faves?innersrc=uriapi）上 `window.amap.get/post` 可用：
- GET  /service/fav/getFav?     读全量 + ver
- POST /service/fav/syncFaves?  合并提交

实测限制：
- 一次性提交几百条会被服务端静默丢弃（返回 status:1 但不落盘）→ 必须分批
- 单账号收藏总数上限约 300 条
"""
import hashlib
import json
import os
import time

FETCH_SCRIPT = r"""(async function () {
  function get(u) {
    return new Promise(function (res) {
      var t = setTimeout(function () { res(null); }, 15000);
      try { window.amap.get(u, function (d) { clearTimeout(t); res(d); }, 'json'); }
      catch (e) { clearTimeout(t); res(null); }
    });
  }
  var r = await get('/service/fav/getFav?');
  if (!r || String(r.status) !== '1') return JSON.stringify({ ok: false, err: 'not-logged-in' });
  var items = (r.data && r.data.items) || [];
  var rows = items.map(function (it) {
    var d = it.data || {};
    return {
      id: it.id,
      name: d.name || d.custom_name || '',
      address: d.address || d.custom_address || '',
      city: d.cityName || '',
      lng: parseFloat(d.lon != null ? d.lon : 0),
      lat: parseFloat(d.lat != null ? d.lat : 0),
      point_x: d.point_x, point_y: d.point_y,
      schema: d.schemaName || ''
    };
  });
  return JSON.stringify({ ok: true, ver: (r.data && r.data.ver) || '', total: items.length, rows: rows });
})()"""


def item_id(px, py, name):
    return hashlib.md5(f"{px}+{py}+{name}".encode()).hexdigest()


def to_amap_item(row, ts=None):
    """标准化记录 -> 高德 syncFaves 的 item。"""
    from .coords import gcj02_to_amap_pixel

    ts = ts or int(time.time())
    lng, lat = float(row["lng"]), float(row["lat"])
    px, py = gcj02_to_amap_pixel(lng, lat)
    name = (row.get("name") or "").strip()
    addr = (row.get("address") or "").strip()
    iid = row.get("id") if row.get("id") and row.get("from_amap") else item_id(px, py, name)
    return {
        "type": 101, "id": iid, "act": "c", "ts": ts,
        "data": {
            "name": name, "custom_name": name,
            "address": addr, "custom_address": addr,
            "lon": round(lng, 12), "lat": round(lat, 12),
            "point_x": str(px), "point_y": str(py), "x": px, "y": py,
            "item_id": iid, "poiid": "", "type": "0",
            "markerType": "marker-fav", "schemaName": "自定义点",
            "city_code": "", "cityCode": "", "cityName": row.get("city", ""),
            "create_time": f"{ts}.0",
            "create_time_format": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
            "adcode": "", "entranceList": [], "industry": "", "parentID": "",
            "top_time": "", "floor": "", "atag_cid": "", "version": "1",
        },
    }


IMPORT_TEMPLATE = r"""(async function () {
  const ITEMS = __ITEMS__;
  const BATCH = __BATCH__;
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function get(u) {
    return new Promise(res => {
      const t = setTimeout(() => res(null), 15000);
      try { window.amap.get(u, d => { clearTimeout(t); res(d); }, 'json'); }
      catch (e) { clearTimeout(t); res(null); }
    });
  }
  function post(u, body) {
    return new Promise(res => {
      const t = setTimeout(() => res({ status: 'timeout' }), 120000);
      try { window.amap.post(u, body, d => { clearTimeout(t); res(d); }, 'json'); }
      catch (e) { clearTimeout(t); res({ status: 'err', msg: String(e).slice(0, 200) }); }
    });
  }

  const first = await get('/service/fav/getFav?');
  if (!first || String(first.status) !== '1') {
    return JSON.stringify({ ok: false, err: 'not-logged-in' });
  }
  const start = ((first.data && first.data.items) || []).length;
  const have0 = new Set(((first.data && first.data.items) || []).map(i => i.id));
  let pending = ITEMS.filter(it => !have0.has(it.id));
  const log = ['start=' + start + ' pending=' + pending.length];
  if (!pending.length) return JSON.stringify({ ok: true, start: start, final: start, added: 0 });

  for (let i = 0; i < pending.length; i += BATCH) {
    const chunk = pending.slice(i, i + BATCH);
    const c = await get('/service/fav/getFav?');
    if (!c || String(c.status) !== '1') { log.push('read-fail'); break; }
    const cur = (c.data && c.data.items) || [];
    const ver = (c.data && c.data.ver) || '';
    const merged = new Map();
    for (const x of cur) if (x && x.id && x.data) merged.set(x.id, x);
    for (const it of chunk) merged.set(it.id, it);
    const url = (window.amap.service && window.amap.service.syncFaves) || '/service/fav/syncFaves?';
    const r = await post(url, { data: Array.from(merged.values()), ver });
    const good = r && (String(r.status) === '1' || (r.data && r.data.code === 1));
    log.push('batch ' + (i / BATCH + 1) + ' submit=' + merged.size + ' ' + (good ? 'OK' : 'FAIL'));
    await sleep(3000);
  }

  for (let round = 1; round <= 3; round++) {
    const a = await get('/service/fav/getFav?');
    const nowHave = new Set(((a && a.data && a.data.items) || []).map(i => i.id));
    const still = ITEMS.filter(it => !nowHave.has(it.id));
    log.push('reconcile ' + round + ': have=' + nowHave.size + ' missing=' + still.length);
    if (!still.length) break;
    if (round === 3) {
      log.push('unimported: ' + still.map(x => x.data.name).join('、'));
      break;
    }
    for (const it of still) {
      const cc = await get('/service/fav/getFav?');
      if (!cc || String(cc.status) !== '1') break;
      const ver = (cc.data && cc.data.ver) || '';
      const merged = new Map();
      for (const x of ((cc.data && cc.data.items) || [])) if (x && x.id && x.data) merged.set(x.id, x);
      merged.set(it.id, it);
      await post((window.amap.service && window.amap.service.syncFaves) || '/service/fav/syncFaves?',
                 { data: Array.from(merged.values()), ver });
      await sleep(5000);
    }
    await sleep(5000);
  }

  const fin = await get('/service/fav/getFav?');
  const final = fin && fin.data && fin.data.items ? fin.data.items.length : -1;
  return JSON.stringify({ ok: true, start: start, final: final, target: ITEMS.length, log: log });
})()"""


def build_import_script(rows, batch=50):
    items = [to_amap_item(r) for r in rows if r.get("name") and r.get("lng") and r.get("lat")]
    js = IMPORT_TEMPLATE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)).replace("__BATCH__", str(batch))
    return js, len(items)


def parse_fetch_result(raw_json_text):
    data = json.loads(raw_json_text) if isinstance(raw_json_text, str) else raw_json_text
    if not data.get("ok"):
        raise RuntimeError(f"AMap fetch failed: {data.get('err')}")
    rows = []
    for r in data.get("rows", []):
        if not r.get("lng") or not r.get("lat"):
            continue
        rows.append({
            "source": "amap",
            "id": r.get("id", ""),
            "name": (r.get("name") or "").strip(),
            "address": (r.get("address") or "").strip(),
            "city": (r.get("city") or "").strip(),
            "lng": round(float(r["lng"]), 6),
            "lat": round(float(r["lat"]), 6),
            "from_amap": True,
        })
    return rows, data.get("ver", "")


def save_script(js, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    return path
