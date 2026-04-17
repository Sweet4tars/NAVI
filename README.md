# Travel Planner Agent

本地运行的中国境内旅游规划系统，提供 `Web 页面` 和 `Codex skill / CLI` 两种入口。

## 功能

- 采集旅游攻略、小红书笔记摘要、12306 车次、高德路线估算、OTA 酒店候选
- 自动生成按天行程、交通建议、酒店推荐和预算快照
- 复用本机浏览器登录态；如果某站点需要登录，会提示你先登录一次再继续
- Web 页面和 CLI 共用一套后端与规划逻辑
- 浏览器优先级固定为 `Edge -> 项目持久化 Chromium -> Chrome`

## 当前站点策略

- `小红书`：抓取搜索结果页的攻略笔记摘要、POI 和提示语
- `携程`：使用手机版酒店列表页，优先提取真实酒店卡片；价格不可见时会标记为 `price-hidden`
- `美团`：使用 `guide.meituan.com/stay/<city>` 城市住宿攻略页，提取价位段、片区和品牌建议
- `去哪儿`：使用 `getCitySuggestV4` 提取城市热搜片区和地标，先作为住宿检索片区建议源
- `飞猪`：使用 `CitySuggest.do` 获取城市 code，并拼装 `hotel_list3.htm` 结果页；若未登录则明确进入 `awaiting_login`

## Docs

- `docs/design-borrowing.md`
- `docs/qunar-fliggy-roadmap.md`

## 安装

```powershell
cd D:\code\travel-planner-agent
python -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -e .[dev]
playwright install chromium
```

可选环境变量：

```powershell
$env:AMAP_API_KEY="你的高德 Web 服务 Key"
$env:TRAVEL_PLANNER_BROWSER_HEADLESS="false"
```

## 启动 Web

```powershell
.venv\Scripts\python -m travel_planner.cli serve --host 127.0.0.1 --port 8091
```

打开 `http://127.0.0.1:8091`。

## CLI / Codex 用法

```powershell
.venv\Scripts\python -m travel_planner.cli plan `
  --origin 上海 `
  --destination 苏州 `
  --start-date 2026-05-01 `
  --days 3 `
  --adults 2 `
  --transport-mode rail
```

## Qunar Debug Tools

Capture live Qunar hotel requests with the agent browser profile:

```powershell
.venv\Scripts\python -m travel_planner.cli qunar-capture
```

For Qunar specifically, prefer visible mode when chasing hotel list payloads. Headless mode may receive downgraded suggestion data.

Replay a captured request by URL substring:

```powershell
.venv\Scripts\python -m travel_planner.cli qunar-replay `
  --capture-file .data\qunar-captures\session-YYYYMMDD-HHMMSS\session.json `
  --match hotel
```

## 说明

- 12306 走只读官方查询接口，不代购票。
- 酒店与小红书依赖网页抓取，页面结构或风控变化时会降级为 `partial_result`。
- 未登录时系统不会保存或导出 cookie，只会复用本机已有浏览器资料目录；若不可用，则退回项目自己的持久化浏览器资料目录并提示先登录一次。
