# Omniship Air Waybills PoC

本项目用于验证从 `https://crossborder.omniship.eu/air_waybills` 自动抓取 Air Waybills 数据，写入 PostgreSQL，并在 Next.js 内部后台中展示、搜索和查看详情。

## 目录结构

```text
.
├── backend/            # FastAPI + SQLAlchemy + Alembic + Playwright
├── frontend/           # Next.js 内部后台
├── docker-compose.yml  # 本地 PostgreSQL，可选
├── .env.example        # 环境变量模板
└── README.md
```

## 环境变量

复制模板并填写真实配置：

```powershell
Copy-Item .env.example .env
```

关键变量：

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/omniship_poc
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

OMNISHIP_BASE_URL=https://crossborder.omniship.eu
OMNISHIP_LOGIN_URL=https://crossborder.omniship.eu/
OMNISHIP_AIR_WAYBILLS_URL=https://crossborder.omniship.eu/air_waybills
OMNISHIP_AIR_WAYBILLS_CREATE_URL=https://crossborder.omniship.eu/air_waybills/create
OMNISHIP_USERNAME=your_email@example.com
OMNISHIP_PASSWORD=your_password
PLAYWRIGHT_HEADLESS=false
PLAYWRIGHT_TIMEOUT_MS=30000
ALLINE_PRE_ALERT_UPLOAD_TIMEOUT_MS=180000
ALLINE_PREVIEW_VALIDATION_TIMEOUT_MS=120000
OMNISHIP_INCREMENTAL_STOP_AFTER_UNCHANGED=10
AIR_WAYBILL_AUTO_REFRESH_ENABLED=true
AIR_WAYBILL_AUTO_REFRESH_INTERVAL_SECONDS=3600
AIR_WAYBILL_AUTO_REFRESH_INITIAL_DELAY_SECONDS=3600

AUTH_SESSION_TTL_HOURS=12
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=integrer_session
UPLOAD_STORAGE_DIR=backend/storage/uploads
```

`.env` 已在 `.gitignore` 中排除。前端只读取 `NEXT_PUBLIC_API_BASE_URL`，不会接触 Omniship 账号密码。上传文件默认保存到 `backend/storage/uploads`，该目录已从版本库排除。

## Windows 10 本地启动

准备：

- Python 3.12+
- Node.js 20+
- PostgreSQL 14+，或 Docker Desktop

启动 PostgreSQL，可选：

```powershell
docker compose up -d postgres
```

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m playwright install chromium
cd backend
python -m alembic upgrade head
python -m app.cli create-admin
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

访问 [http://localhost:3000/air-waybills](http://localhost:3000/air-waybills)。未登录会跳转到 `/login`。

## Ubuntu 24.04 部署准备

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib
```

PostgreSQL 初始化示例：

```bash
sudo -u postgres psql
CREATE DATABASE omniship_poc;
CREATE USER omniship_user WITH PASSWORD 'change_me';
GRANT ALL PRIVILEGES ON DATABASE omniship_poc TO omniship_user;
\q
```

后端：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m playwright install --with-deps chromium
cd backend
python -m alembic upgrade head
python -m app.cli create-admin
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run build
npm run start -- --host 0.0.0.0 --port 3000
```

生产环境建议设置 `PLAYWRIGHT_HEADLESS=true` 和 `AUTH_COOKIE_SECURE=true`。

## 账号与权限

- 第一个管理员使用 CLI 创建：`python -m app.cli create-admin`
- 管理员可以创建普通账号、启用/禁用账号、重置密码、触发 Waybills 更新。
- 普通账号只能查看、搜索 Waybills 和查看详情。
- 登录态使用 HttpOnly Cookie：`integrer_session`。
- 审计日志会记录登录、退出、用户管理和触发更新等操作。

## 更新策略

- `全量更新`：翻页读取 Air Waybills 列表的全部数据，并进入每个 Actions 链接抓取详情和 Destinations。
- `立即更新`：进入列表后会尽量把 `Rows per page` 设置为 25，并确保按 `Status Changed` 最近活动优先排序；随后从第一页开始向后读取。
- 增量判断只比较稳定业务字段：`Status`、`Weight(kg)`、`Received`、`Parcels`、`In Warehouse`、`Released`、`Out Bound`。`Status Changed` 只用于目标系统排序，不再展示，也不参与变化判断。
- 已抓取且稳定业务字段未变化的单号不会重复进入详情页；新增或稳定字段变化的单号会重新抓取详情。
- 当连续遇到 `OMNISHIP_INCREMENTAL_STOP_AFTER_UNCHANGED` 条旧且未变化的数据后，立即停止翻页；默认值为 10。
- 后端服务启动后会按 `AIR_WAYBILL_AUTO_REFRESH_INTERVAL_SECONDS` 自动执行一次 `立即更新`；默认每 3600 秒执行一次。首次自动执行默认延迟 3600 秒，避免服务启动时立刻占用 Playwright。
- 如果已有抓取任务处于 `running`，自动更新会跳过本轮，避免与手动 `全量更新` 或 `立即更新` 重叠。
- Actions 列只读取可见文本和链接地址，不执行原系统里的新增、删除、编辑、导出等写操作。

## API

- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/users`，仅管理员
- `POST /api/v1/users`，仅管理员
- `PATCH /api/v1/users/{userId}`，仅管理员
- `POST /api/v1/users/{userId}/reset-password`，仅管理员
- `POST /api/v1/air-waybills/scrape`，仅管理员，兼容旧的同步抓取接口
- `POST /api/v1/air-waybills/refresh`，仅管理员，启动增量更新任务
- `POST /api/v1/air-waybills/full-refresh`，仅管理员，启动全量更新任务
- `GET /api/v1/air-waybills/scrape-runs/{runId}`，仅管理员，读取任务进度
- `GET /api/v1/air-waybills/latest`，登录用户
- `GET /api/v1/air-waybills/{number}`，登录用户，读取详情页数据
- `GET /api/v1/air-waybills/scrape-status`，仅管理员
- `GET /api/v1/waybill-uploads`，管理员读取全部上传记录，普通用户只读取自己的上传记录
- `POST /api/v1/waybill-uploads`，保留纯文本票号绑定接口
- `POST /api/v1/waybill-uploads/file`，上传 Pre Alert 表单与附件
- `PATCH /api/v1/waybill-uploads/{uploadId}/status`，仅管理员审核上传记录
- `DELETE /api/v1/waybill-uploads/{uploadId}`，仅删除本系统上传记录、附件和本地票号绑定，不会删除 ALLINE 数据

## 测试

后端：

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

前端：

```powershell
cd frontend
npm test
npm run lint
npm run build
```

数据库迁移 SQL 检查：

```powershell
cd backend
..\.venv\Scripts\python -m alembic upgrade head --sql
```

## 数据归属与上传

- 管理员可以查看全部 Waybills，包括历史抓取产生的未绑定数据。
- 普通用户只能查看与自己账号绑定的 Waybill Number；未绑定数据不会出现在普通用户列表和详情接口中。
- `/waybill-uploads` 提供 Pre Alert 上传窗口，管理员和普通用户都可以上传。普通用户上传并平台提交成功后自动绑定到自己；管理员可选择目标用户。
- 上传字段包括 `Platform`、`Shipment Type`、`Air Waybill Number`、`Air Waybill Gross Weight (KG)`、`Air Waybill Pieces`、可选的 `Arrival Flight Number`、PDF Air Waybill 文件和 Excel Customer Pre Alert 文件。
- `Platform` 一期只支持 `ALLINE`，对应 `https://crossborder.omniship.eu/`；后续适配其他系统时在该单选列表中追加选项。
- 后端会校验票号是否已有成功提交记录、重量和件数是否为数字、PDF 单个文件小于 10MB、Excel 文件小于 20MB。PDF 会检查文件头，Excel 一期先按扩展名校验 `.xls` / `.xlsx`。
- 平台提交成功后才写入票号绑定，因此该用户可以在 Waybills 列表和详情中查询自己的票号进度；失败记录会保留用于排查，但不会占用票号，用户可修正后再次提交同一票号。
- 删除上传记录只影响本系统：会删除上传记录、附件和由该上传创建的本地票号绑定，不会对 ALLINE 执行删除。
- 对 `ALLINE` 平台，后端会继续使用 Playwright 打开 `OMNISHIP_AIR_WAYBILLS_CREATE_URL`，按 `Create Waybill -> Upload Pre Alert File -> Map Fields -> Preview and confirm` 四步提交到原系统。
- `ALLINE_PRE_ALERT_UPLOAD_TIMEOUT_MS` 用于等待 ALLINE 接收并解析 Customer Pre Alert 文件；Excel 较大或网络较慢时可调大。
- `ALLINE_PREVIEW_VALIDATION_TIMEOUT_MS` 用于等待 ALLINE 第四步 Preview validation 完成；页面提示最多 1 分钟，默认保留 120 秒余量。
- 平台提交结果与管理员审核状态分开记录：`platformSubmissionStatus` 为 `pending` / `success` / `failed`，失败时会保存 `platformSubmissionError`，便于管理员排查。
