# 分享查看与 PDF 导出设计

## 目标

这份设计解决两个问题：

1. 行程生成后，怎么方便发给别人查看
2. 行程如何在“可交互查看”和“离线转发”之间平衡

基于当前项目结构，推荐的主方案不是直接发 `PDF`，而是：

- 主入口：`只读分享页`
- 辅入口：`PDF 导出`
- 数据底座：`结果快照`

当前项目已经具备这条路的基础条件：

- 服务端：`FastAPI`
- 页面层：`Jinja2 Templates`
- 存储：`SQLite`
- 结果页：已有 [result.html](../travel_planner/templates/result.html)
- 任务与结果持久化：已有 [database.py](../travel_planner/database.py)

所以第一版不需要做“共享社区”，只需要在现有结果页链路上补一层“可分享快照”。

## 为什么不是只发 PDF

PDF 当然要做，但只能做辅助手段，原因如下：

- PDF 适合微信转发、打印、离线查看
- PDF 不适合地图联动、候选切换、来源跳转、行程微调
- 行程一旦修改，旧 PDF 很快过期
- 旅游计划本质上是动态信息，天然更适合网页

结论：

- `分享链接` 负责“查看”
- `PDF` 负责“存档、打印、转发”

## 第一版产品形态

生成一个行程后，系统同时给出三种产物：

1. `结果页`
   - 当前用户在站内查看
   - 路径示例：`/results/{job_id}`
2. `分享页`
   - 发给别人查看的只读页面
   - 路径示例：`/share/{token}`
3. `PDF`
   - 从分享页导出
   - 路径示例：`/share/{token}.pdf`

这样做有三个好处：

- 用户心智清楚：站内编辑，站外分享
- 分享页不依赖登录态和抓取流程
- PDF 可以直接从分享页渲染，避免维护两套内容

## 推荐交互流程

### 生成后

用户完成一次规划后，在 [result.html](../travel_planner/templates/result.html) 页面新增按钮：

- `创建分享链接`
- `复制链接`
- `导出 PDF`

### 创建分享链接

点击后：

1. 服务端读取 `job.result`
2. 生成一份不可变的 `分享快照`
3. 生成一个随机 `token`
4. 返回分享地址

### 分享页查看

别人打开分享页后，默认只读，不触发任何实时抓取，不需要登录，也不依赖当前浏览器的 OTA 登录态。

### 行程修改后

如果原计划被重排或改动：

- 旧分享链接仍然指向旧快照
- 用户可以手动创建“新分享链接”
- 不自动覆盖旧分享内容

这是关键设计。分享页必须读快照，而不是读当前实时结果。

## 核心原则：分享的是快照，不是任务

当前项目的核心实体是 `JobRecord`，定义在 [schemas.py](../travel_planner/schemas.py)。

但 `job` 的职责是“任务执行过程”，并不等于“可分享成果”。原因：

- job 可能仍在 `collecting`
- job 可能后续被 `resume`
- job 可能被重新规划，结果发生变化

因此新增一层最稳：

- `TripShareSnapshot`
- `TripShareLink`

也就是：

- `JobRecord` 负责生成
- `ShareSnapshot` 负责分享

## 数据模型设计

建议在 [database.py](../travel_planner/database.py) 新增两张表。

### 1. `trip_share_snapshot`

用途：

- 保存某次分享时冻结下来的完整展示数据

建议字段：

```sql
CREATE TABLE IF NOT EXISTS trip_share_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

说明：

- `summary_json` 存完整展示 JSON
- 内容应该直接来自 `job.request + job.result`
- 这里不要只存引用，应该存冗余快照，保证之后 job 变化也不影响分享页

### 2. `trip_share_link`

用途：

- 保存分享 token、权限、过期策略

建议字段：

```sql
CREATE TABLE IF NOT EXISTS trip_share_link (
    token TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'token',
    passcode TEXT NOT NULL DEFAULT '',
    expires_at TEXT,
    created_at TEXT NOT NULL,
    last_accessed_at TEXT
);
```

说明：

- `visibility` 第一版只需要支持：
  - `token`
  - `passcode`
- `expires_at` 可空，允许永久链接
- `passcode` 第一版可以先存明文；第二版再改哈希

## 分享快照 JSON 结构

建议新增一个分享专用 schema，而不是直接把 `JobRecord` 原样暴露。

推荐结构：

```json
{
  "meta": {
    "title": "宜宾集合 · 云南自驾 6 天",
    "origin": "宜宾",
    "destination": "云南",
    "start_date": "2026-04-30",
    "end_date": "2026-05-05",
    "generated_at": "2026-04-17T11:30:00+08:00",
    "updated_at": "2026-04-17T11:30:00+08:00",
    "share_version": 1
  },
  "summary": "...",
  "daily_itinerary": [],
  "transport_options": [],
  "hotel_candidates": [],
  "budget_estimate": {},
  "source_evidence": [],
  "guide_notes": [],
  "pois": [],
  "warnings": [],
  "display": {
    "show_sources": true,
    "show_candidates": true,
    "show_budget": true
  }
}
```

这样做的价值：

- 分享页展示层和任务执行层彻底解耦
- 后续可以按分享场景裁剪字段
- PDF 可以直接复用同一个结构

## 后端接口设计

建议在 [main.py](../travel_planner/main.py) 增加以下接口。

### 1. 创建分享链接

```text
POST /api/trips/{job_id}/share
```

请求示例：

```json
{
  "visibility": "token",
  "expires_in_days": 30,
  "passcode": ""
}
```

返回示例：

```json
{
  "token": "trp_xxxxx",
  "share_url": "/share/trp_xxxxx",
  "expires_at": "2026-05-17T11:30:00+08:00"
}
```

### 2. 获取分享元信息

```text
GET /api/share/{token}
```

用途：

- 供网页异步加载
- 供小程序/H5 后续复用

### 3. 分享页 HTML

```text
GET /share/{token}
```

用途：

- 浏览器直接打开
- Jinja 模板渲染即可

### 4. 导出 PDF

```text
GET /share/{token}.pdf
```

用途：

- 返回 PDF 下载

### 5. 失效分享链接

```text
POST /api/share/{token}/revoke
```

用途：

- 用户主动废弃已发出的链接

## 页面设计

### 1. 结果页

在现有 [result.html](../travel_planner/templates/result.html) 上增加一个“分享工具条”：

- `创建分享链接`
- `复制分享链接`
- `导出 PDF`
- `二维码`

建议放在页面头部 summary 区域附近，不要埋太深。

### 2. 分享页

新增模板：

- `share.html`

建议结构：

1. 顶部摘要区
   - 标题
   - 日期
   - 出发地 / 目的地
   - 人数
   - 更新时间
2. 地图总览区
   - 第一版可先放占位图或路线摘要
   - 第二版再接动态地图
3. 每日时间线
   - Day 1 ~ Day N
   - 上午 / 下午 / 晚上 / 住宿
4. 交通与驾驶强度
   - 总里程
   - 预计车程
   - 高强度日期提示
5. 酒店候选
   - 酒店名
   - 价格
   - 推荐理由
   - 来源链接
6. 餐饮与来源
   - 店名
   - 推荐理由
   - 来源链接
7. 预算
   - 交通 / 酒店 / 餐饮
8. 风险提醒
   - 登录态不保证
   - 价格可能变动

### 3. PDF 版式

PDF 页面不要完全复制分享页交互结构，而要做打印优化：

- A4 纵向
- 简化颜色
- 去掉复杂交互
- 保留二维码跳转到在线分享页

PDF 应保留：

- 行程摘要
- 每日安排
- 住宿和核心餐饮推荐
- 预算
- 二维码

## PDF 技术方案

推荐顺序：

### 第一版

直接用浏览器打印样式：

- 分享页增加 `print.css`
- 使用 `window.print()` 或服务端浏览器渲染 PDF

### 第二版

使用 `Playwright` 服务端导出：

- 项目本身已使用 Playwright 浏览器链路
- 可以新增一个 PDF 导出服务，访问 `/share/{token}?print=1`
- 再通过 Playwright 的 `page.pdf()` 生成文件

选择 Playwright 的原因：

- 与现有项目依赖方向一致
- 页面即 PDF，维护成本低
- 对中文排版和复杂布局更稳

## 权限与安全

第一版只需要做轻量权限，不要把系统做重。

### 推荐支持

- `token-only`
  - 知道链接即可查看
  - 默认方案
- `token + passcode`
  - 发群时更安全
- `expires_at`
  - 例如 7 天 / 30 天 / 永久

### 第一版不建议做

- 账号登录后授权谁能看
- 组织空间
- 公开搜索引擎可见
- 分享评论区

### 安全注意点

- 分享页只读，不允许触发重新抓取
- 分享快照中不要包含登录态、cookie、调试信息
- 如果来源链接有敏感 query 参数，入库前要清洗
- 默认给 `noindex`，避免搜索引擎抓取

## 现有代码里的最小改动点

### 1. Schema 层

文件：

- [schemas.py](../travel_planner/schemas.py)

建议新增：

- `ShareVisibility`
- `TripShareCreateRequest`
- `TripShareSnapshot`
- `TripShareLink`

### 2. Repository 层

文件：

- [database.py](../travel_planner/database.py)

建议新增方法：

- `create_share_snapshot(...)`
- `create_share_link(...)`
- `get_share_by_token(...)`
- `revoke_share_link(...)`
- `touch_share_access(...)`

### 3. Service 层

文件：

- [service.py](../travel_planner/service.py)

建议新增方法：

- `create_share(job_id, visibility, passcode, expires_in_days)`
- `get_share(token, passcode=None)`
- `build_share_snapshot(job)`
- `export_share_pdf(token)`

### 4. Web 层

文件：

- [main.py](../travel_planner/main.py)

建议新增路由：

- `POST /api/trips/{job_id}/share`
- `GET /api/share/{token}`
- `GET /share/{token}`
- `GET /share/{token}.pdf`
- `POST /api/share/{token}/revoke`

### 5. 模板层

文件：

- [result.html](../travel_planner/templates/result.html)
- 新增 `share.html`
- 新增 `print-share.html` 或共用 `share.html`

### 6. 样式层

文件：

- [style.css](../travel_planner/static/style.css)

建议新增：

- 分享工具条样式
- 只读分享页样式
- 打印样式 `@media print`

## 分阶段实施建议

### Phase 1：先把分享链路跑通

目标：

- 一键生成分享链接
- 分享页可打开
- 读取冻结快照

范围：

- SQLite 两张分享表
- 创建分享 API
- 分享页模板
- 结果页按钮

这是最值得先做的阶段。

### Phase 2：补 PDF

目标：

- 分享页支持导出 PDF
- PDF 可直接转发、打印

范围：

- 打印样式
- Playwright 生成 PDF
- 页面内二维码

### Phase 3：补“多人查看体验”

目标：

- 密码访问
- 访问过期
- 访问统计

范围：

- passcode 校验
- expires_at 生效
- last_accessed_at 记录

### Phase 4：再考虑轻量共享平台

目标：

- 用户可以管理自己创建过的分享链接
- 支持复制一个计划另存为新版本

范围：

- “我的分享”
- 失效管理
- 克隆计划

注意：这还不是公开社区，只是分享管理后台。

## 不建议第一版做的事

- 公开旅游广场
- 他人在线编辑同一份计划
- 评论系统
- 点赞收藏
- SEO 开放抓取
- 分享页实时回源重新抓 OTA 和小红书

这些都会让系统复杂度暴涨，但并不能最先提升可用性。

## 推荐结论

对你这个项目，最合适的路线是：

1. 先做 `分享快照 + 分享链接`
2. 再做 `PDF 导出`
3. 最后才考虑“共享平台”

一句话概括：

> 第一版做“可分享的只读行程页”，不是做“旅游社区”。

## 下一步实现顺序

如果要直接开始做，建议按下面顺序改代码：

1. 在 [schemas.py](../travel_planner/schemas.py) 增加分享相关 schema
2. 在 [database.py](../travel_planner/database.py) 增加分享表和 repository 方法
3. 在 [service.py](../travel_planner/service.py) 加分享快照创建逻辑
4. 在 [main.py](../travel_planner/main.py) 增加 `/share` 和 `/api/share` 路由
5. 新增 `share.html`
6. 修改 [result.html](../travel_planner/templates/result.html) 增加“创建分享链接 / 导出 PDF”按钮
7. 最后补 `Playwright PDF`

