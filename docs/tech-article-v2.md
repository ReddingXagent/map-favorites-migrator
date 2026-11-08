## 先说做什么

一个开源命令行工具，在**百度地图**和**高德地图**之间双向搬收藏。

```bash
pip install -e .
mfm fetch baidu                                  # 生成抓取脚本
mfm parse baidu --input raw.json --out places.json
mfm convert --from baidu --to amap --input places.json --out import.js
```

**开源地址**：https://github.com/ReddingXagent/map-favorites-migrator

## 主要功能

- **双向转换**：百度 → 高德，高德 → 百度
- **坐标自动换算**：两家坐标系不同，内置转换，误差控制在几十米内
- **分批提交**：避开高德写入限流，每批提交后自动核对
- **一键脱敏**：手机号、身份证、门牌号打码，坐标降精度，方便分享
- **纯本地运行**：只跟你浏览器登录的官网通信，不经过任何第三方服务器

用法就是在两个网站的控制台各跑一段脚本，中间用命令行转换。不需要账号密码，只用你已登录的浏览器状态。

## 遇到的情况和解决办法

### 一、开放平台 Key 用不了

第一反应是申请高德的 Web 服务 Key，调 `/v3/favorite/add`。

结果返回 `SERVICE_NOT_AVAILABLE`。

查文档才明白：**服务端 API 是只读的**。搜索、逆地理、路径规划能查，但收藏属于用户账号数据，权限在网页端登录态里，Key 拿不到。

顺带一提，百度那份「地图收藏夹」文档是**安卓 SDK 的本地收藏夹**，数据只存在手机 App 自己的目录里，跟云端账号完全不互通。看标题容易走错路。

### 二、百度收藏接口返回的不是列表

正确入口是网页端接口 `qt=fav&mode=get&type=favdata`。

但返回的是**增量变更流**——同一条收藏会出现好几条记录：先 `add`，后来改标签变成 `modify`，删除则是 `del`。

我第一版直接筛 `action === 'add'`，数量比手机 App 显示的少了一大截。

正确做法是**按 sid 分组取最新版本**，再剔除已删除的。另外别用「页码变化」判断是否拉完，要看响应里的 `newnum`（服务端剩余条数）归零。

### 三、网传的坐标算法偏了将近一公里

百度返回的坐标是墨卡托格式。网上流传最广的那份「官方 MC2LL 系数表」，我用实际地点验证，偏移接近一公里。

后来用几个已知地点反推，拟合出自己的公式：

```python
def bd_mc_to_gcj(x, y):
    lat = y / 111320.0
    for _ in range(80):
        rp = 171.233889 * lat + 6335150.13
        nl = math.degrees(2 * math.atan(math.exp(y / rp)) - math.pi / 2)
        if abs(nl - lat) < 1e-11:
            lat = nl; break
        lat = nl
    return math.degrees(x / 6378551.0), lat
```

误差压到几十米内。

**还有个容易多此一举的地方**：反解出来已经是高德能用的坐标系了，很多教程会让你再加一次偏移——那等于又偏回去。

### 四、高德写入返回成功，但数据没进去

高德现在走 `/api/favorite/add`，可以逐条加；老页面上的 `syncFaves` 也还能用，走「读全量 → 合并 → 一次提交」更稳。

问题是：一次性提交几百条，接口返回 `status: 1`、`message: "Successful."`，看起来完美，读回来一看**条数没变**。

解决办法是**分批提交**，每批之前重新读一次版本号，避免冲突：

```javascript
for (let i = 0; i < pending.length; i += BATCH) {
  const cur = await get('/service/fav/getFav?');
  const merged = new Map();
  for (const x of cur.data.items) merged.set(x.id, x);
  for (const it of pending.slice(i, i + BATCH)) merged.set(it.id, it);
  await post('/service/fav/syncFaves?', {
    data: Array.from(merged.values()),
    ver: cur.data.ver
  });
  await sleep(3000);
}
```

另外，高德账号的收藏有数量上限。到顶之后无论怎么提交都进不去，接口照样返回成功。这时候只能先删旧的腾位置。

### 五、页面渲染不出来（这个最折腾）

调试时遇到：高德页面骨架能出来，但 `window.amap` 是 `undefined`，地图区域一片空白。

排查了半天才发现，是**日常 Chrome 的扩展或缓存**污染了页面。

换成全新的独立配置启动就好：

```bash
chrome --remote-debugging-port=9225 \
       --remote-allow-origins=* \
       --user-data-dir=/tmp/oc-clean \
       --disable-extensions \
       'https://ditu.amap.com/faves?innersrc=uriapi'
```

另外地址必须带 `?innersrc=uriapi`，否则会被重定向到新版页面，新版在部分环境下渲染不出来。

顺便说个操作上的观察：页面里可能存在透明的模态层盖住整个视口，这时候所有坐标点击都会失效。用 `document.elementFromPoint()` 检查一下实际命中的元素，能省很多时间。

### 六、编辑器改了内容，但保存的是旧的

这个问题跟迁移无关，但同样值得记一笔。

CSDN 这类站点用的是自研编辑器（cledit），有自己的内部状态。直接 `element.textContent = 内容` 只改了 DOM，编辑器不知道，提交的还是旧内容。

正确做法是模拟一次真实输入：

```javascript
element.focus();
const sel = window.getSelection();
const range = document.createRange();
range.selectNodeContents(element);
sel.removeAllRanges();
sel.addRange(range);
document.execCommand('insertText', false, content);
```

## 小结

| 情况 | 关键点 |
|---|---|
| API Key 用不了 | 收藏是用户数据，只能走登录态 |
| 接口像列表其实是变更流 | 按 sid 取最新版本，剔删除 |
| 坐标偏一公里 | 网传公式不可信，实测校准 |
| 写入报成功但没数据 | 分批 + 读回核对 + 注意容量上限 |
| 页面空白 | 独立配置 + 禁用扩展 |
| 编辑器改了没生效 | 用 insertText，别直接改 textContent |

完整代码和说明都在仓库里：

**https://github.com/ReddingXagent/map-favorites-migrator**

工具只处理你自己账号的收藏，不做批量爬取。数据全程留在本地，分享前记得跑一下脱敏。
