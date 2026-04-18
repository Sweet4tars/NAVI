# Cloudflared 公网分享

## 当前实现

项目已经内置了两层能力：

1. `cloudflared` 快速隧道启动 / 停止 / 状态查询
2. 动态 share 生成时自动返回公网绝对链接

同时，针对同一个 `job_id`：

- 新 share 生成时，会自动停用旧 token
- 被停用的旧链接再访问会返回 `404`

## 常用命令

先启动本地服务：

```powershell
cd <repo-root>
.\.venv\Scripts\python -m travel_planner.cli serve --host 127.0.0.1 --port 8091
```

再启动 `cloudflared`：

```powershell
cd <repo-root>
.\.venv\Scripts\python -m travel_planner.cli cloudflared-start `
  --binary "C:\Program Files (x86)\cloudflared\cloudflared.exe" `
  --target-url http://127.0.0.1:8091
```

查看当前公网域名：

```powershell
.\.venv\Scripts\python -m travel_planner.cli cloudflared-status
```

停止隧道：

```powershell
.\.venv\Scripts\python -m travel_planner.cli cloudflared-stop
```

## 运行时文件

启动成功后，项目会写入：

- 公网基址: `.data/runtime/public_base_url.txt`
- tunnel pid: `.data/runtime/cloudflared.pid`
- tunnel 日志: `.data/logs/cloudflared.out.log`

FastAPI 在创建 share 时会读取这个公网基址，并直接返回：

- `public_share_url`
- `public_excel_url`
- `public_pdf_url`

## API

创建动态分享：

```text
POST /api/trips/{job_id}/share
```

查询当前公网基址：

```text
GET /api/share/public-base-url
```

手动停用单个 share：

```text
DELETE /api/shares/{token}
```

## 当前约束

- 这版默认走 `trycloudflare.com` 的快速隧道，域名是临时的，但比 `localtunnel` 稳定。
- 如果后续要换成固定子域名，需要再接 Cloudflare Named Tunnel。
