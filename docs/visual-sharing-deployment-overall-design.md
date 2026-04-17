# 可视化结果页 + 分享页 + 最小部署整体设计

## 目标

这份设计把三件事合在一起：

1. `可视化结果页` 怎么设计
2. `可分享的只读行程页` 怎么落地
3. `服务端怎么部署` 才既不破坏本机登录态，又能把结果发给别人看

这份文档不是抽象产品稿，而是基于当前项目现状整理的：

- 当前后端：`FastAPI`
- 当前页面：`Jinja2`
- 当前存储：`SQLite`
- 当前规划输出：`TripPlanResult`
- 当前运行方式：本机启动，默认 `127.0.0.1:8091`

相关代码位置：

- [main.py](D:/code/travel-planner-agent/travel_planner/main.py)
- [cli.py](D:/code/travel-planner-agent/travel_planner/cli.py)
- [schemas.py](D:/code/travel-planner-agent/travel_planner/schemas.py)
- [service.py](D:/code/travel-planner-agent/travel_planner/service.py)
- [database.py](D:/code/travel-planner-agent/travel_planner/database.py)
- [result.html](D:/code/travel-planner-agent/travel_planner/templates/result.html)
- [style.css](D:/code/travel-planner-agent/travel_planner/static/style.css)

## 当前现实约束

先把约束说清楚，否则部署和分享方案会跑偏。

### 1. 规划能力依赖本机浏览器登录态

当前项目的 OTA、小红书链路依赖本机浏览器资料目录与登录态，不能直接假设可以搬到云上继续工作。

### 2. Web 服务默认是本机服务

当前 CLI 默认这样启动：

```powershell
.venv\Scripts\python -m travel_planner.cli serve --host 127.0.0.1 --port 8091
```

这意味着默认只有本机能访问。

### 3. 当前结果页还不是“可视化分享页”

当前 [result.html](D:/code/travel-planner-agent/travel_planner/templates/result.html) 主要是三列卡片：

- 每日行程
- 交通 / 酒店
- 攻略 / 预算 / 来源

它已经是“结果展示页”，但还不是目标中的“可视化、可分享、可部署”的成品页。

### 4. 当前 schema 还缺关键展示数据

这是最重要的一条。当前 [schemas.py](D:/code/travel-planner-agent/travel_planner/schemas.py) 虽然已经有：

- `DailyPlan`
- `TransportOption`
- `HotelCandidate`
- `PoiCandidate`
- `GuideNote`

但还缺下面这些可视化必须字段：

- `酒店坐标`
- `POI 坐标`
- `路线分段 route legs`
- `餐饮候选`
- `每日餐饮与住宿挂钩关系`
- `分享快照 schema`
- `分享版本 version`

所以第一版整体设计必须先解决“数据够不够展示”的问题。

## 总体架构结论

推荐采用两层架构：

### A. 本机规划端

职责：

- 复用本机登录态
- 爬取小红书 / OTA / 12306 / 地图数据
- 生成 `TripPlanResult`
- 创建分享快照

这部分继续跑在你的电脑上。

### B. 分享展示端

职责：

- 读取冻结后的分享快照
- 展示只读可视化行程页
- 导出 PDF

第一版可以和本机规划端跑在同一服务里。后面再拆分成独立的公网只读服务。

一句话：

> 规划过程依赖本机，分享结果不依赖本机登录态。

## 视觉与交互方案

## 一、页面角色划分

建议整个系统分成 3 种页面，不要混在一起。

### 1. 输入页

用途：

- 填出发地、目的地、人数、日期、出行方式、预算、偏好

当前已有：

- [index.html](D:/code/travel-planner-agent/travel_planner/templates/index.html)

### 2. 结果页

用途：

- 给当前操作用户看
- 支持继续刷新、重跑、查看数据源状态
- 支持创建分享链接

当前已有雏形：

- [result.html](D:/code/travel-planner-agent/travel_planner/templates/result.html)

### 3. 分享页

用途：

- 给别人看
- 只读
- 不触发重新采集
- 可导出 PDF

需要新增：

- `share.html`

## 二、结果页视觉结构

建议采用 `左时间线 + 右摘要与候选 + 顶部分享工具条`。

### 顶部 Hero

显示：

- 行程标题
- 日期范围
- 人数
- 交通方式
- 总预算
- 数据更新时间

右上角加工具按钮：

- `创建分享链接`
- `复制链接`
- `导出 PDF`
- `查看分享页`

### 主体布局

#### 左列：每日时间线

按 Day 1 ~ Day N 展开：

- 主题
- 上午
- 下午
- 晚上
- 住宿
- 驾驶强度标签

#### 中列：交通与路线

显示：

- 主要交通方式
- 自驾总里程 / 时长 / 费用
- 关键长途日提示
- 路线摘要图或地图占位

#### 右列：候选与来源

显示：

- 酒店候选
- 餐饮候选
- 攻略摘录
- 预算
- 来源链接

### 当前 UI 与目标 UI 的差距

当前 [result.html](D:/code/travel-planner-agent/travel_planner/templates/result.html) 里：

- 已有每日卡片
- 已有酒店候选
- 已有来源证据

但还缺：

- 分享工具条
- 餐饮候选结构化展示
- 驾驶强度显式区块
- 地图区块
- 更适合分享的摘要头部

## 三、分享页视觉结构

分享页不要完全照搬结果页。

### 分享页原则

- 更干净
- 更易读
- 更少运维功能
- 更像“成品”

### 推荐结构

#### 顶部摘要

- 标题
- 出发地 / 目的地
- 日期
- 人数
- 生成时间
- 预算摘要

#### 地图总览

第一版可以做 2 档：

- 有地图 key：渲染真实地图
- 没有地图 key：显示路线摘要卡 + 城市节点卡

#### 每日时间线

每一天显示：

- 主题
- 上午 / 下午 / 晚上
- 住宿
- 驾驶强度

#### 住宿推荐

每个酒店卡片显示：

- 名称
- 区位
- 价格
- 推荐理由
- 来源链接

#### 餐饮推荐

每个餐饮卡片显示：

- 名称
- 餐段
- 推荐理由
- 来源平台
- 来源链接

#### 风险与备注

- 价格可能变动
- 节假日排队风险
- 登录态只影响采集阶段，不影响分享页查看

## 四、地图可视化的方案

当前项目还没有地图前端层，所以必须收敛第一版范围。

### 第一版推荐

不要一开始就做复杂交互地图，先做：

- 城市节点地图
- POI 标注
- 酒店标注
- 简化路线连线

### 第二版再做

- 拖拽改点
- 局部重排
- 地图选点反馈规划

## 技术选型建议

如果继续沿用当前 Jinja + 静态 CSS 方案：

- 第一版地图可直接用前端嵌入的地图 SDK
- 中国场景优先建议高德 JS API

原因：

- 当前项目已经有 `AMAP_API_KEY` 配置
- [map.py](D:/code/travel-planner-agent/travel_planner/connectors/map.py) 已经使用高德做 POI 与驾车估算
- 同一地图服务商更容易让 POI、路线、分享页显示一致

### 地图前提

要上真实地图，schema 必须补：

- `PoiCandidate.lat`
- `PoiCandidate.lng`
- `HotelCandidate.lat`
- `HotelCandidate.lng`

当前还没有这些字段。

## 分享逻辑

分享页的底层逻辑必须是“快照分享”。

不是分享：

- `job_id`
- 当前运行中的任务
- 实时页面

而是分享：

- 某一时刻冻结出来的结果快照

具体逻辑已经在 [sharing-platform-design.md](D:/code/travel-planner-agent/docs/sharing-platform-design.md) 里展开，这里只定总原则：

1. 用户在结果页点击“创建分享链接”
2. 服务端读取 `job.result`
3. 生成 `TripShareSnapshot`
4. 生成 `token`
5. 别人访问 `/share/{token}` 时只读快照

## 最小部署方案

## 一、开发模式

适合本机调试。

启动方式：

```powershell
.venv\Scripts\python -m travel_planner.cli serve --host 127.0.0.1 --port 8091
```

特点：

- 只有本机可访问
- 最安全
- 最适合开发

## 二、局域网分享模式

适合同一 Wi-Fi 或办公室临时查看分享页。

启动方式：

```powershell
.venv\Scripts\python -m travel_planner.cli serve --host 0.0.0.0 --port 8091
```

然后访问：

```text
http://<你的局域网IP>:8091/share/<token>
```

前提：

- 本机防火墙允许端口
- 电脑不能关机
- 只建议临时用

## 三、本机 + 公网穿透模式

适合第一版给外部朋友看。

结构：

- 本机继续跑完整服务
- 用穿透工具把 `8091` 暴露出去
- 分享页通过公网 URL 访问

优点：

- 快速
- 不需要单独服务器

缺点：

- 稳定性弱
- 电脑必须在线
- 安全面更大

## 四、长期推荐模式

长期更推荐：

### 本机规划端

- 保留登录态抓取
- 保留人工验证
- 继续跑采集和规划

### 公网分享端

- 只保存分享快照
- 只提供 `/share/{token}`
- 只提供 PDF 导出

这才是未来最稳的生产形态。

## 结果数据模型的必须升级项

这是这次检查里最关键的部分。

如果不改 schema，分享页只能做成“静态结果卡片”，做不成真正的可视化成品页。

## 当前已经有的结构

在 [schemas.py](D:/code/travel-planner-agent/travel_planner/schemas.py) 里，当前有：

- `DailyPlan`
- `TransportOption`
- `HotelCandidate`
- `PoiCandidate`
- `GuideNote`
- `TripPlanResult`

## 当前缺失但必须补的结构

### 1. 餐饮候选模型

当前结果里没有结构化 `RestaurantCandidate`。

这会直接导致：

- 分享页无法单独展示餐饮推荐
- PDF 无法稳定输出每顿饭
- 只能靠 Markdown 文案兜底

建议新增：

```python
class RestaurantCandidate(BaseModel):
    source: str
    name: str
    city: str = ""
    district: str = ""
    meal_slot: Literal["breakfast", "lunch", "dinner", "snack"] = "dinner"
    rating: float | None = None
    review_count: int | None = None
    cuisine: str = ""
    recommendation_reason: str = ""
    booking_url: str = ""
```

### 2. 坐标字段

当前 `PoiCandidate` 没有坐标，`HotelCandidate` 也没有坐标。

建议补：

- `lat`
- `lng`

否则地图只能显示文字，不能渲染点位。

### 3. 路线分段模型

当前 `TransportOption` 更像“总交通方案”，不是“路线分段”。

但可视化页想显示：

- 宜宾 -> 昆明
- 昆明 -> 大理
- 大理 -> 昆明
- 昆明 -> 宜宾

就需要独立的 `RouteLeg`。

建议新增：

```python
class RouteLeg(BaseModel):
    day_index: int
    origin: str
    destination: str
    duration_minutes: int = 0
    distance_km: float = 0
    toll_fee: float | None = None
    fuel_fee: float | None = None
    source: str = ""
```

### 4. 分享快照模型

当前没有：

- `TripShareSnapshot`
- `TripShareLink`

这个在 [sharing-platform-design.md](D:/code/travel-planner-agent/docs/sharing-platform-design.md) 里已经定了。

### 5. 可视化专用显示元数据

当前 `DailyPlan` 只有三段文案：

- morning
- afternoon
- evening

但分享页还需要：

- 驾驶强度
- 住宿点
- 是否长途日
- 当日预算摘要

建议补一个更偏展示的数据层，而不是继续往 `DailyPlan` 里硬塞。

## 还没有确定、必须锁定的细节

下面这些是这次检查后确认仍未定的点。它们不是“以后再说”的小问题，而是会影响设计收口的关键决策。

## 一、地图到底上不上第一版

现状：

- 有高德后端数据能力
- 没有前端地图层
- 没有坐标字段

建议拍板：

- 第一版：`支持静态路线摘要 + 可选真实地图`
- 如果没有坐标或 key，就降级成路线卡片，不阻塞分享页上线

## 二、餐饮推荐是否正式入结果 schema

现状：

- 旅游案例里已经人工整理了餐饮候选
- 但项目正式输出里还没有 `RestaurantCandidate`

建议拍板：

- 必须正式入 schema
- 否则“可视化分享页”只会有酒店，没有餐饮，和用户真实需求不符

## 三、分享链接是否允许永久有效

现状：

- 方案里提了 `expires_at`
- 但默认值还没定

建议拍板：

- 默认 `30 天`
- 支持 `永久`
- 第一版先不做自动清理任务，只在访问时校验过期

## 四、passcode 是否第一版就做

现状：

- 设计里有 passcode
- 但第一版如果做，会多一层表单和校验页

建议拍板：

- 第一版先只做 `token-only`
- 第二版再做 `passcode`

## 五、PDF 是前端打印还是服务端 Playwright

现状：

- 两条路都能走

建议拍板：

- 第一版：浏览器打印样式
- 第二版：服务端 `Playwright PDF`

理由：

- 第一版最省实现量
- 当前项目已经在用 Playwright，后续迁移自然

## 六、分享页是和规划端同服务，还是单独服务

现状：

- 当前只有一个 FastAPI 服务

建议拍板：

- 第一版：仍然同服务
- 第二版：抽离成独立只读分享服务

## 七、外部分享 URL 的域名怎么来

现状：

- 当前配置里没有 `BASE_URL`
- 分享 API 如果返回相对路径，发给别人不够用

建议必须新增配置：

- `TRAVEL_PLANNER_BASE_URL`

例如：

```text
http://127.0.0.1:8091
http://192.168.1.23:8091
https://trip.example.com
```

否则分享链接无法稳定生成“可直接复制给别人”的绝对 URL。

## 八、分享快照里是否保留来源链接全文

现状：

- `source_evidence` 已有 `title / url / excerpt`

建议拍板：

- 第一版保留来源 URL 和摘录
- 不缓存网页全文

理由：

- 降低存储复杂度
- 减少版权和内容陈旧问题

## 九、结果修改后的分享版本策略

现状：

- 设计上已经偏向“新版本新链接”

建议拍板：

- 不覆盖旧分享
- 每次重新分享创建新快照
- 结果页提供“最近一次分享链接”显示

## 最小可用版本定义

如果按现实约束收敛，最小可用版本应该是：

### 功能

- 输入页正常规划
- 结果页支持“创建分享链接”
- 分享页支持只读查看
- 分享页支持酒店、攻略、预算、每日行程展示
- 分享页支持来源跳转
- 支持基本 PDF 打印

### 降级接受

- 没有真实地图时，用路线摘要卡代替
- 没有餐饮 schema 前，餐饮先不上分享页主结构

但这里我明确建议：

- 最小可用版上线前，最好先补 `RestaurantCandidate`

因为餐饮是你这个产品的核心卖点之一。

## 推荐实施顺序

### Phase 0：先补数据模型

必须先做：

1. `RestaurantCandidate`
2. `lat/lng`
3. `RouteLeg`
4. `TripShareSnapshot / TripShareLink`
5. `TRAVEL_PLANNER_BASE_URL`

### Phase 1：可分享只读页

实现：

1. 结果页增加分享按钮
2. 分享表入库
3. `/share/{token}` 页面
4. token-only 访问

### Phase 2：可视化增强

实现：

1. 地图区块
2. 路线摘要
3. 餐饮卡片
4. 驾驶强度显示

### Phase 3：部署增强

实现：

1. 局域网 / 穿透模式配置
2. `BASE_URL` 正常返回
3. PDF 导出

### Phase 4：独立分享服务

实现：

1. 分享快照同步到公网
2. 分享端只读服务
3. 主规划端继续留本机

## 最终建议

对当前项目，最合理的整体路线是：

1. `本机规划端` 保留，不动根
2. 先把 `结果页 -> 分享快照 -> 只读分享页` 打通
3. 分享页第一版以 `时间线 + 酒店/餐饮卡片 + 来源链接 + 路线摘要` 为主
4. 地图作为增强项，不应阻塞分享功能上线
5. 长期再拆分为 `本机规划端 + 公网只读分享端`

一句话总结：

> 先把“能稳定分享的成品页”做出来，再把它升级成“有地图的可视化成品页”。

