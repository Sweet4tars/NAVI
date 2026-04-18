# Navigation-AI-for-Voyages-and-Itineraries

面向中国境内出行场景的旅游规划 Agent。项目把攻略采集、交通查询、酒店候选、预算汇总、分享页导出放到一条链路里，提供 `Web 页面`、`CLI` 和 `Codex skill` 三种入口。

## 项目现在能做什么

- 采集旅游攻略、小红书笔记摘要、12306 车次、高德路线估算、OTA 酒店候选
- 生成按天行程、交通建议、酒店推荐、预算快照和来源证据
- 复用本机浏览器登录态；如果站点需要登录，会明确提示先人工登录一次
- 生成只读分享页，并支持 `Excel / PDF / 公网分享`
- 支持按 source checkpoint 恢复，避免登录或验证后整单重跑

## 当前实现范围

- 场景：大陆境内旅行规划
- 交通：`rail` / `drive`
- 浏览器策略：`Edge -> 项目持久化 Chromium -> Chrome`
- 产品边界：只做规划，不代下单，不绕过官方限制

## 数据源现状

- `小红书`：抓取搜索结果页摘要、POI 和提示语
- `12306`：只读查询
- `高德`：POI 搜索、驾车估算、前端地图展示
- `携程`：手机版酒店列表页优先提取真实酒店卡片
- `美团`：城市住宿攻略页提取片区与价位建议
- `飞猪`：城市建议与酒店列表页已接入，必要时进入 `awaiting_login`
- `去哪儿`：当前已降级为片区提示，不再作为主酒店源

## 系统结构

- `travel_planner/main.py`
  FastAPI 入口、页面路由、分享接口
- `travel_planner/service.py`
  规划编排、checkpoint 恢复、share payload 生成
- `travel_planner/connectors/`
  小红书、12306、OTA、地图等数据接入
- `travel_planner/templates/`
  表单页、结果页、案例分享页
- `travel_planner/static/style.css`
  整体前端样式

## 快速开始

```powershell
cd <repo-root>
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .[dev]
playwright install chromium
```

可选环境变量：

```powershell
$env:AMAP_API_KEY="你的高德 Web 服务 Key"
$env:AMAP_JS_API_KEY="你的高德 JS API Key"
$env:AMAP_SECURITY_JS_CODE="你的高德安全密钥"
$env:TRAVEL_PLANNER_BROWSER_HEADLESS="false"
```

启动 Web：

```powershell
.\.venv\Scripts\python -m travel_planner.cli serve --host 127.0.0.1 --port 8091
```

打开 `http://127.0.0.1:8091`。

## 常用命令

同步规划一条行程：

```powershell
.\.venv\Scripts\python -m travel_planner.cli plan `
  --origin 上海 `
  --destination 苏州 `
  --start-date 2026-05-01 `
  --days 3 `
  --adults 2 `
  --transport-mode rail
```

启动临时公网分享：

```powershell
.\.venv\Scripts\python -m travel_planner.cli cloudflared-start `
  --binary "C:\Program Files (x86)\cloudflared\cloudflared.exe" `
  --target-url http://127.0.0.1:8091
```

查看公网分享状态：

```powershell
.\.venv\Scripts\python -m travel_planner.cli cloudflared-status
```

发布前脱敏检查：

```powershell
.\.venv\Scripts\python -m travel_planner.publish_check
```

或：

```powershell
python scripts/prepublish_check.py
```

## 开源发布前建议

推送前至少做这几件事：

1. 跑一次发布检查脚本，确认没有本机绝对路径、局域网 IP、临时公网隧道地址和疑似密钥。
2. 确认 `.data/`、浏览器 profile、日志、导出文件没有被纳入版本管理。
3. 不要把真实 Cookie、调试 HAR、数据库、导出 Excel / PDF 推到远程仓库。

## 安全与隐私边界

- 项目不会替你下单、抢票或绕过平台规则。
- 项目不要求导出 Cookie 文件；只复用本机已有浏览器登录态。
- 分享页读取的是快照，不会在他人访问时重新触发抓取。
- 生成的公网 URL 应视为临时公开链接，敏感案例不要长期暴露。

## 相关文档

- `docs/design-borrowing.md`
- `docs/qunar-fliggy-roadmap.md`
- `docs/sharing-platform-design.md`
- `docs/visual-sharing-deployment-overall-design.md`
- `docs/cloudflared-sharing.md`

## 当前重点方向

- 继续提高真实酒店候选质量和价格可信度
- 把餐饮候选从案例数据继续推进到动态 share 链路
- 继续完善分享页、导出链路和公开部署体验
