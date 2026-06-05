# Waybill Pre Alert 上传管理系统

本项目是一个内部后台系统：用户登录后上传 Pre Alert（PDF Air Waybill 文件 + Excel Customer Pre Alert 文件），数据校验后入库保存；管理员可以查看、下载、审核（通过/拒绝）和删除上传记录。后续将逐步加入人工订单状态维护与邮件发送流程。

## 目录结构

```text
.
├── backend/            # FastAPI + SQLAlchemy + Alembic
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
FRONTEND_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

AUTH_SESSION_TTL_HOURS=12
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=integrer_session
UPLOAD_STORAGE_DIR=backend/storage/uploads
```

`.env` 已在 `.gitignore` 中排除。前端只读取 `NEXT_PUBLIC_API_BASE_URL`。上传文件默认保存到 `backend/storage/uploads`，该目录已从版本库排除。

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

访问 [http://localhost:3000/](http://localhost:3000/) 查看落地页；登录成功后进入 `/waybill-uploads`。未登录访问受保护页面会跳转到 `/login`。

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

生产环境建议设置 `AUTH_COOKIE_SECURE=true`。

## 账号与权限

- 第一个管理员使用 CLI 创建：`python -m app.cli create-admin`
- 管理员可以创建普通账号、启用/禁用账号、重置密码，并查看、下载、审核和删除全部上传记录。
- 普通账号只能上传 Pre Alert 并查看自己的上传记录。
- 登录态使用 HttpOnly Cookie：`integrer_session`。
- 审计日志会记录登录、退出、用户管理、上传、审核、下载和删除等操作。

## API

- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/users`，仅管理员
- `POST /api/v1/users`，仅管理员
- `PATCH /api/v1/users/{userId}`，仅管理员
- `POST /api/v1/users/{userId}/reset-password`，仅管理员
- `GET /api/v1/waybill-uploads`，管理员读取全部上传记录，普通用户只读取自己的上传记录
- `POST /api/v1/waybill-uploads/file`，上传 Pre Alert 表单与附件
- `POST /api/v1/waybill-uploads/pre-alert`，上传 Pre Alert 表单与附件（别名路径）
- `PATCH /api/v1/waybill-uploads/{uploadId}/status`，仅管理员审核上传记录
- `GET /api/v1/waybill-uploads/{uploadId}/files/{fileId}/download`，下载上传的附件
- `DELETE /api/v1/waybill-uploads/{uploadId}`，删除本系统的上传记录和附件

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

- 管理员可以查看全部上传记录；普通用户只能查看自己的上传记录。
- `/waybill-uploads` 提供 Pre Alert 上传窗口，管理员和普通用户都可以上传。普通用户上传的记录归属于自己；管理员可以选择目标用户。
- 上传字段包括 `Shipment Type`、`Air Waybill Number`、`Air Waybill Gross Weight (KG)`、`Air Waybill Pieces`、可选的 `Arrival Flight Number`、PDF Air Waybill 文件和 Excel Customer Pre Alert 文件。
- 后端会校验重量和件数是否为数字、PDF 单个文件小于 10MB、Excel 文件小于 20MB。PDF 会检查文件头，Excel 一期先按扩展名校验 `.xls` / `.xlsx`，并对 Excel 内容执行 Pre Alert 业务校验（违禁品名称、同一收件人/地址申报金额上限等）。
- 上传成功后记录默认状态为 `pending_review`，管理员可以将其改为 `approved` 或 `rejected`。
- 删除上传记录只影响本系统：会删除上传记录及其附件，不会对外部系统执行任何操作。
