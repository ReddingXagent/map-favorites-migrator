# 排障手册

实战踩过的坑，按症状查。

## 1. 只导入了 102 条，但手机显示 319 条

**原因**：百度 `qt=fav&mode=get&type=favdata` 是**增量同步流**，同一 `sid` 会出现多条记录（`add` / `modify` / `del`）。

错误写法：`all.filter(x => x.action === 'add')` —— 会把后来 `modify` 过的条目全丢掉。

正确写法：按 `sid` 取 `ver` 最大的那条，再剔除 `action === 'del'`：

```js
const best = {};
all.forEach(x => {
  const v = parseInt(x.ver || '0', 10);
  if (!best[x.sid] || v > parseInt(best[x.sid].ver || '0', 10)) best[x.sid] = x;
});
const alive = Object.keys(best).map(k => best[k]).filter(x => x.action !== 'del');
```

判定标准：`sync.newnum` 归零才说明拉完。`newnum` 是**服务端剩余条数**，比 `lastver` 变化更可靠。

## 2. 高德页面空白 / `window.amap` 是 undefined

**症状**：页面能出骨架，但 `typeof window.amap === 'undefined'`，`canvas` 数量为 0。

**原因**：旧 Chrome profile 的扩展或缓存污染了高德渲染；或页面被 302 到 `/ssr/*` 新架构（新架构在这个环境里渲染失败）。

**解决**：
1. 用**独立 user-data-dir** 起 Chrome：
   ```
   chrome.exe --remote-debugging-port=9225 --remote-allow-origins=* \
     --user-data-dir=C:\Temp\oc-amap-clean --disable-extensions \
     'https://ditu.amap.com/faves?innersrc=uriapi'
   ```
2. 用 `?innersrc=uriapi` 入口，避免 302 到 `/ssr/faves`。
3. 验证：`typeof window.amap.post === 'function'` 且 `document.querySelectorAll('canvas').length >= 1`。

## 3. 登录了但还是读不到收藏

**症状**：`getFav` 返回 HTML（77KB 左右）而不是 JSON。

**原因**：cookie 没带上或已过期。检查 amap 域下的 cookie 里有没有 `_m_h5_tk`、`cna`、`loginToken` 之类；只有 `xlly_s / isg / tfstk / amig` 是纯匿名态。

**解决**：在 `/faves` 页面点右上角，用手机高德 App 扫码登录。`passport.amap.com` 直连可能 `ERR_INVALID_RESPONSE`，别走这条路。

## 4. `syncFaves` 返回 status:1，但条数没变

**症状**：提交成功，读回数量不变。

**原因**：高德服务端对单次提交的条数有限制，超大的 payload 会被静默丢弃（不报错）。实测一次性提交 339 条 → 全部丢失；分批 50 条 → 成功。

**解决**：分批提交（`--batch 50`），每批前重新读 `ver`，每批后 sleep 3 秒。

## 5. 补漏跑了无数轮，还是差 30 条

**症状**：`getFav` 稳定在某个数字不再增长，剩余条目反复提交无效。

**原因**：**高德单账号收藏总数上限约 300 条**（不是限流，是硬上限）。超出部分无论怎么提交都进不去。

**解决**：
- 先删高德里的旧收藏腾位
- 或者接受部分导入，把剩余条目导成 CSV 留档
- 不要无限重试，多试 2~3 轮足够了

## 6. 坐标对不上（偏几百米到几公里）

**症状**：导入后高德地图上的点位置明显偏移。

**原因**：百度 `geoptx/geopty` 是 BD09 墨卡托。网上流传的官方 `MC2LL` 系数表（`LLBAND` + `LL2MC` 六档）反解出来偏 ~700m——那套算法的分档系数与现代 BD09MC 数据不匹配。

**解决**：用本 skill 的 `coord.py`（实测校准，误差 <25m）：

```python
lng, lat = mc2gcj(bd_mercator_x, bd_mercator_y)
# lng = degrees(x / 6378551.0)
# lat: 迭代解 y = (171.233889·lat + 6335150.13) · ln(tan(π/4 + lat/2))
```

反算结果**已经是 GCJ02 量级**，不要再叠加 BD09→GCJ02 偏移（否则再偏 700m）。

## 7. CDP 脚本执行返回 `{"type":"undefined"}`

**原因**：表达式是语句（`var x = ...;`）而非表达式，没有返回值。或者 IIFE 未 `return`。

**解决**：包成 IIFE 并显式 `return`：

```js
(function(){ return something; })()
```

异步场景用 `(async function(){ return await foo(); })()`，并确保调用方开了 `awaitPromise: true`。

## 8. PowerShell 写文件后中文变乱码

**原因**：`Set-Content -Encoding UTF8` 在部分环境下写出 GBK，或者 `-replace` 处理中文时损坏多字节字符。

**解决**：用 Python 写文件，别用 PowerShell 做中文文本替换：

```python
open(path, 'w', encoding='utf-8').write(content)
```

## 9. 导出 JSON 变成 UTF-16 乱码

**原因**：用 PowerShell `>` 重定向 Python 输出，PowerShell 默认写 UTF-16LE。

**解决**：让 Python 自己写文件（`open(..., 'w', encoding='utf-8')`），不要经 shell 重定向。
