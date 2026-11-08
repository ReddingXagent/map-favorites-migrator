# mfm · 百度 / 高德地图收藏双向迁移

把**百度地图**和**高德地图**的「地点收藏」互相搬家。双向、可脱敏、纯本地运行。

> 不依赖任何付费 API。用的是两个网页端自己的登录态接口。

---

## 为什么需要它

换地图 App 最大的成本不是导航，是**收藏了几百个地点搬不走**。

- 百度地图 → 高德：高德没有「导入百度收藏」功能
- 高德地图 → 百度：百度同样没有
- 高德 Web 服务 Key **不能**写收藏（`/v3/favorite/add` 返回 `SERVICE_NOT_AVAILABLE`）

这个工具用浏览器登录态直接读写两边的收藏接口，加上实测校准的坐标转换。

---

## 能力

| 方向 | 状态 |
|---|---|
| 百度 → 高德 | ✅ 实测 318 条，成功 307 条（97%） |
| 高德 → 百度 | ✅ 已实现，坐标往返误差 <1m |
| 脱敏导出 | ✅ 手机号/身份证/门牌号打码 + 坐标降精度 |
| CSV / JSON 导出 | ✅ |
| 纯本地运行 | ✅ 只与地图官网通信，无第三方服务 |

**坐标精度**：百度墨卡托 → GCJ02，实测误差 **<25 米**（对比 6 个真实 POI 校准）。

---

## 快速开始

```bash
git clone https://github.com/dingxinyou-hue/map-favorites-migrator.git
cd map-favorites-migrator
pip install -e .
```

### 1. 抓取源数据

```bash
# 生成抓取脚本
mfm fetch baidu --out scripts/fetch_baidu.js
```

打开 `https://map.baidu.com`（先登录），F12 控制台粘贴脚本内容，回车。复制返回值存成 `baidu_raw.json`。

```bash
mfm parse baidu --input baidu_raw.json --out baidu.json
```

同理抓高德：打开 `https://ditu.amap.com/faves?innersrc=uriapi`（先登录），运行 `mfm fetch amap` 生成的脚本，存成 `amap_raw.json`，然后 `mfm parse amap --input amap_raw.json --out amap.json`。

### 2. 转换并导入

```bash
# 百度 -> 高德
mfm convert --from baidu --to amap --input baidu.json --out import_amap.js
```

打开高德收藏页（已登录），控制台粘贴 `import_amap.js` 内容执行。脚本会分批提交并自动核对。

```bash
# 高德 -> 百度
mfm convert --from amap --to baidu --input amap.json --out import_baidu.js
```

### 3. 脱敏导出（分享/开源前）

```bash
mfm redact --input baidu.json --out baidu_redacted.json
mfm export --input baidu_redacted.json --format csv --out baidu.csv
```

脱敏规则：
- 手机号、身份证、固话 → `<PHONE>` / `<ID>` / `<TEL>`
- 门牌号/房号/楼栋 → `<NUM>`
- 坐标降精度到 0.01°（约 1km）

---

## 关键实现细节（踩过的坑）

### 百度收藏是增量流，不是列表

`qt=fav&mode=get&type=favdata` 返回的是**变更流**：同一 `sid` 会有 `add` / `modify` / `del` 多条记录。

❌ 错误：`all.filter(x => x.action === 'add')` → 实测只拿到 102 条（真实 318 条）
✅ 正确：按 `sid` 取 `ver` 最大的那条，再剔除 `action === 'del'`

判定拉完的依据是 `sync.newnum` 归零（服务端剩余条数），不是 `lastver` 变化。

### 坐标：别用网上的百度官方算法

网上流传的 `MC2LL` 六档系数表（`LLBAND` + `LL2MC`）在 BD09 墨卡托数据上偏 **~700 米**。

本项目实测校准的公式：

```
lng = degrees(x / 6378551.0)
lat：迭代解 y = (171.233889·lat + 6335150.13)·ln(tan(π/4 + lat/2))
```

结果直接是 GCJ02 量级，**不要**再叠加 BD09→GCJ02 偏移。

### 高德收藏有容量上限

实测单账号约 **300 条**。到顶后 `syncFaves` 仍返回 `status:1`，但服务端不落盘，反复重试无效。

另外一次性提交几百条也会被静默丢弃，必须分批（默认 50 条/批）。

### 高德页面渲染

- 必须用 `?innersrc=uriapi` 入口，否则 302 到新 `/ssr/*` 架构
- 部分 Chrome profile 下 `window.amap` 挂载失败 → 用独立 user-data-dir + `--disable-extensions`

详见 [docs/troubleshooting.md](docs/troubleshooting.md)。

---

## 隐私与合规

- **全部本地运行**，数据不经过任何服务器
- 只读取你自己账号的收藏，不涉及他人数据
- 请勿用于批量爬取或违反平台协议的场景
- 分享数据前请用 `mfm redact` 脱敏

---

## 许可

MIT
