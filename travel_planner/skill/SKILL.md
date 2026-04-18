---
name: domestic-travel-planner-skill
description: >-
  Plan domestic China trips using local browser login state, 12306 train lookup,
  OTA hotel page scraping, and a local FastAPI/CLI backend. Keywords: travel,
  trip, itinerary, hotel, rail, drive, xiaohongshu, ctrip, meituan, qunar, fliggy.
license: MIT
metadata:
  author: OpenAI Codex
  version: 0.1.0
  created: 2026-04-16
  last_reviewed: 2026-04-16
  review_interval_days: 90
---
# /domestic-travel-planner-skill - 中国境内旅游规划

你负责把用户的出发地、目的地、日期、人数和出行方式，转换为本地旅游规划请求，并调用当前机器上的 `travel-planner-agent`。

## Trigger

User invokes `/domestic-travel-planner-skill` followed by their input:

```text
/domestic-travel-planner-skill 上海到苏州，五一 3 天，2 大人，铁路，预算 600
/domestic-travel-planner-skill 杭州去安吉，两天一晚，自驾，带孩子，酒店要停车
```

## Workflow

1. 先把缺失参数补齐，只追问缺的字段：
   - `origin`
   - `destination`
   - `start_date`
   - `days` 或 `end_date`
   - `travelers.adults`
   - `transport_mode`
2. 优先调用本地 CLI：

```powershell
cd <repo-root>
.venv\Scripts\python -m travel_planner.cli plan --origin <起点> --destination <终点> --start-date <YYYY-MM-DD> --days <天数> --adults <人数> --transport-mode <rail|drive>
```

3. 如果用户补充了儿童、预算、酒店偏好、停车要求，把对应参数一起带上。
4. 若结果中的 `warnings` 提示某平台需要登录，明确告诉用户：
   - 先在本机浏览器登录对应平台一次
   - 然后重新运行同一个命令
5. 最终输出时按这 5 个块组织：
   - 行程摘要
   - 每日安排
   - 交通建议
   - 酒店候选
   - 预算与风险提示

## Guardrails

- 不代用户下单，不提供抢票或绕过官方限制的建议。
- 如果 12306 / OTA / 小红书数据为空，照常给出降级方案，并明确哪些来源缺失。
- 不要求用户导出 cookie；只允许复用本机浏览器现有登录态，或提示用户先登录一次。
- 浏览器选择顺序固定为 `Edge -> 项目持久化 Chromium -> Chrome`，除非 Edge 不可用，否则不要主动切到别的浏览器。
