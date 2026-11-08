# CSDN / 掘金 技术文章版

> 仓库：https://github.com/ReddingXagent/map-favorites-migrator

**推荐标题**（CSDN 偏好长标题 + 关键词堆叠）：

- 百度地图收藏迁移到高德：踩了 4 个坑，我写了个开源工具（318 条实测）
- 百度地图收藏怎么导入高德？Web 服务 Key 根本不行，得用登录态
- 百度墨卡托坐标转 GCJ-02 偏了 700 米？我反推了校准公式

**分类**：CSDN → 后端/Python；掘金 → 前端 / 工具效率
**标签**：Python、爬虫、地图、坐标转换、开源

---

# 百度地图收藏迁移到高德：踩了 4 个坑，我写了个开源工具

## 背景

换了主力地图 App，几百个收藏搬不走。

高德没有「导入百度收藏」功能，百度也没有反向的。搜了一圈，能用的方案要么收费，要么要账号密码。

自己动手，最后跑通了：**318 条百度收藏 → 307 条成功进高德**。

本文把踩过的坑和完整实现都记下来，代码开源在 GitHub。

---

## 坑 1：官方 API Key 不能写收藏

第一反应是用高德开放平台的 Web 服务 Key。

```bash
curl "https://restapi.amap.com/v3/favorite/add?key=xxx&id=B0FF..."
```

返回：

```json
{"status":"0","info":"SERVICE_NOT_AVAILABLE","infocode":"10002"}
```

翻文档才明白：**Web 服务 API 是只读的**。搜索、逆地理、路径规划、坐标转换这些能查，但收藏属于**用户账号数据**，只能走用户登录态。

顺带说个坑：百度那份「地图收藏夹」文档（`lbsyun.baidu.com/docs/android?title=androidsdk/guide/tool/favorite`）是**安卓 SDK 的本地收藏夹**，数据存在 `data/data/<包名>/files` 下，跟云端账号收藏完全不互通。别被标题骗了。

---

## 坑 2：百度收藏接口是增量流，不是列表

正确入口是网页端接口：

```
GET https://map.baidu.com/?newmap=1&reqflag=pcmap&biz=1&from=webmap
    &da_par=direct&pcevaname=pc4.1&qt=fav&mode=get&type=favdata
    &limit=100&lastver=<游标>&newfrom=zhuzhan_webmap
```

响应：

```json
{
  "result": {"error": 0, "type": 2000},
  "sync": {
    "newdata": [
      {"sid": "11_xxx", "action": "add", "ver": "459612938", "detail": {"data": {...}}},
      {"sid": "11_xxx", "action": "modify", "ver": "459612939", "detail": {"data": {...}}},
      {"sid": "11_yyy", "action": "del", "ver": "..."}
    ],
    "lastver": "4046533454",
    "newnum": 282
  }
}
```

### 我第一版的错误代码

```python
adds = [x for x in all if x["action"] == "add"]
```

结果：**只拿到 102 条**，手机 App 显示 **319 条**。

### 为什么错

这是**变更流（changelog）**，不是收藏列表。同一条收藏会反复出现：

1. 你收藏 → `action: add`
2. 你改标签 → `action: modify`
3. 你删除 → `action: del`

最早那条 `add` 记录里的数据是**旧的**，光筛 `add` 会漏掉所有后来改过的。

### 正确做法

```python
# 1. 按 sid 分组，取 ver 最大的（= 最新状态）
best = {}
for x in all_records:
    v = int(x.get("ver") or 0)
    if x["sid"] not in best or v > int(best[x["sid"]].get("ver") or 0):
        best[x["sid"]] = x

# 2. 剔除已删除的
alive = [x for x in best.values() if x["action"] != "del"]
```

结果：**318 条**（手机端 319 条，差 1 条是没有坐标的线路收藏）。

### 判定拉完的依据

不要看 `lastver` 是否变化（可能卡住），要看 **`sync.newnum`** —— 这是服务端剩余的待同步条数：

```
第 1 轮: got=100, newnum=282
第 2 轮: got=100, newnum=182
第 3 轮: got=100, newnum=82
第 4 轮: got=82,  newnum=0     ← 拉完
```

---

## 坑 3：百度墨卡托坐标，网传算法偏 700 米

百度收藏返回的 `geoptx` / `geopty` 是 **BD09 墨卡托坐标**（整数）：

```json
{"geoptx": 13523758, "geopty": 3641872}
```

网上流传最广的是「百度官方 MC2LL 系数表」：

```python
LLBAND = [75, 60, 45, 30, 15, 0]
LL2MC = [ [...], [...], [...] ]   # 六个分带的系数
```

我用 6 个已知 POI 实测，**偏差 700 米左右**。

### 反推出来的公式

拿真实坐标做校准，拟合结果：

```python
import math

RX = 6378551.0          # 经度方向的等效半径
A_LAT = 171.2338881546564
B_LAT = 6335150.130210205

def bd_mc_to_gcj(x, y):
    """百度墨卡托 -> GCJ-02"""
    x, y = float(x), float(y)
    lat = y / 111320.0
    for _ in range(80):                       # 迭代解纬度
        rp = A_LAT * lat + B_LAT
        nl = math.degrees(2 * math.atan(math.exp(y / rp)) - math.pi / 2)
        if abs(nl - lat) < 1e-11:
            lat = nl
            break
        lat = nl
    return math.degrees(x / RX), lat
```

误差压到 **25 米以内**。

### 关键：不要再叠加 BD09→GCJ-02 偏移

很多教程会教你：

```python
# ❌ 错误：多此一举
lng, lat = bd_mc_to_bd09(x, y)
lng, lat = bd09_to_gcj02(lng, lat)      # 又偏 700 米
```

反解出来的**已经是 GCJ-02 量级**，直接就能用于高德。再叠一次就前功尽弃。

---

## 坑 4：高德批量写入会静默丢数据

高德 2026 版把老接口都下线了，现在走：

```
POST /api/favorite/add
{"mode":"add", "targetUgcId":"<文件夹id>", "point":{...}}
```

但老页面 `ditu.amap.com/faves?innersrc=uriapi` 上 `syncFaves` 还能用，走「读全量 → 合并 → 一次同步」更稳。

### 问题：接口返回成功，但数据没进去

第一次我一次性提交 339 条：

```json
{"status": "1", "data": {"code": 1, "message": "Successful.", "result": true}}
```

看着完美。读回一查：**条数没变**。

### 解决办法：分批 + 每批重读版本号

```javascript
for (let i = 0; i < pending.length; i += BATCH) {   // BATCH = 50
  const chunk = pending.slice(i, i + BATCH);

  // 每批前重新读，拿最新 ver（避免版本冲突）
  const cur = await get('/service/fav/getFav?');
  const ver = cur.data.ver;

  const merged = new Map();
  for (const x of cur.data.items) merged.set(x.id, x);
  for (const it of chunk) merged.set(it.id, it);

  await post('/service/fav/syncFaves?', {
    data: Array.from(merged.values()),
    ver: ver
  });

  await sleep(3000);   // 别急着下一批
}
```

### 还有个硬上限

分批跑完后核对：

```
批次 1 提交 173 -> OK
批次 2 提交 223 -> OK
批次 3 提交 273 -> OK
批次 4 提交 323 -> timeout
批次 5 提交 289 -> OK
最终：289 条
```

继续补漏，无论怎么重试，**卡在 307 条**就上不去了。

结论：**高德单账号收藏总数上限约 300 条**。这是硬限制，不是限流。

---

## 附赠坑：高德页面在部分 Chrome profile 下渲染失败

调试时遇到的玄学问题：页面能出骨架，但 `window.amap` 是 `undefined`，地图 canvas 数量为 0。

```javascript
typeof window.amap   // "undefined"
```

排查发现：**日常 Chrome profile 里的扩展或缓存污染了页面**。

解决办法：

```bash
chrome.exe --remote-debugging-port=9225 \
  --remote-allow-origins=* \
  --user-data-dir=C:\Temp\oc-amap-clean \
  --disable-extensions \
  'https://ditu.amap.com/faves?innersrc=uriapi'
```

换全新 profile，立刻正常。另外必须带 `?innersrc=uriapi`，否则会 302 到新 `/ssr/*` 架构，那套在部分环境下渲染不出来。

---

## 完整工具

整理成开源命令行了，MIT 协议：

**https://github.com/ReddingXagent/map-favorites-migrator**

```bash
git clone https://github.com/ReddingXagent/map-favorites-migrator.git
cd map-favorites-migrator && pip install -e .
```

### 使用流程

```bash
# 1. 生成抓取脚本
mfm fetch baidu --out fetch.js
#    在 map.baidu.com（已登录）控制台粘贴执行，存返回值

# 2. 解析成标准 JSON
mfm parse baidu --input raw.json --out baidu.json

# 3. 转换并生成导入脚本
mfm convert --from baidu --to amap --input baidu.json --out import.js
#    在高德收藏页控制台执行 import.js

# 4. 脱敏导出（分享前必做）
mfm redact --input baidu.json --out clean.json
mfm export --input clean.json --format csv --out baidu.csv
```

### 支持双向

```bash
mfm convert --from amap --to baidu --input amap.json --out import_baidu.js
```

### 核心模块

```
src/mfm/
├── coords.py        # BD09MC / BD09 / GCJ02 / WGS84 互转
├── baidu.py         # 增量流抓取 + 去重
├── baidu_write.py   # 写入百度（反向）
├── amap.py          # 高德读 + 分批写入
├── redact.py        # 脱敏
└── cli.py           # 命令行
```

### 测试

```python
def test_baidu_mercator_accuracy():
    for (x, y), (elng, elat) in CALIBRATION:      # 6 个真实 POI
        lng, lat = bd_mc_to_gcj(x, y)
        assert haversine(lng, lat, elng, elat) < 60
```

```bash
pytest tests/ -q    # 10 passed
```

### 脱敏做了什么

- 手机号 / 身份证 / 固话 → `<PHONE>` / `<ID>` / `<TEL>`
- 门牌号 / 房号 / 楼栋 → `<NUM>`
- 坐标降精度到 0.01°（约 1km）
- 精确墨卡托坐标同样降精度
- **自检**：脱敏后扫描残留，不干净会告警

---

## 总结

| 坑 | 教训 |
|---|---|
| API Key 不能写 | 收藏是用户态数据，别指望开放平台 |
| 增量流当列表 | 按 `sid` + `ver` 去重，剔除 `del` |
| 坐标偏 700m | 网传官方系数表不可信，实测校准 |
| 批量写入静默失败 | 分批 + 读回核对 + 注意容量上限 |
| 页面渲染失败 | 独立 profile + `--disable-extensions` |

如果你也在换地图 App，希望这能省你两天。

仓库：**https://github.com/ReddingXagent/map-favorites-migrator**
有问题欢迎提 Issue。
