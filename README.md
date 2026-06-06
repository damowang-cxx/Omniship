# Waybill Pre Alert Upload Management

Internal EPIX back-office system for submitting Air Waybill Pre Alert data. Users upload a PDF Air Waybill document and an Excel Customer Pre Alert file; the backend validates the files, stores the upload locally, and lets admins review submitted waybills.

## Project Structure

```text
.
├── backend/            # FastAPI + SQLAlchemy + Alembic
├── frontend/           # Next.js public landing page + internal dashboard
├── docker-compose.yml  # Optional local PostgreSQL
├── .env.example        # Environment template
└── README.md
```

## Environment

Copy the template and fill in local values:

```powershell
Copy-Item .env.example .env
```

Important variables:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/omniship_poc
FRONTEND_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

AUTH_SESSION_TTL_HOURS=12
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_NAME=integrer_session
UPLOAD_STORAGE_DIR=backend/storage/uploads
```

`.env` and `backend/storage/` are ignored by git. Credentials and uploaded files must not be committed.

## Local Development

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
cd backend
python -m alembic upgrade head
python -m app.cli create-admin
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000/](http://localhost:3000/). Unauthenticated users see the public EPIX landing page. Login is available at `/login`; successful login redirects to `/waybill-uploads`.

## Pages And Permissions

- `/` is the public EPIX landing page.
- `/login` is the only public login entry.
- `/waybill-uploads` lets admins and users upload Pre Alert data.
- `/waybill-upload-management` is admin-only and shows all submitted waybills.
- `/users` is admin-only account management.
- Regular users can upload and view only their own upload records.
- Admins can upload for a selected Target User, review all submissions, download attachments, approve/reject records, and delete local records.

## Upload Rules

Upload form fields:

- `Shipment Type`: `Air`, `Road`, or `Train`
- `Target User`: admin-only; regular users are always bound to their own account
- `Air Waybill Number`
- `Air Waybill Gross Weight (KG)`
- `Air Waybill Pieces`
- `Arrival Flight Number`, optional
- `Air Waybill Document(s)`: PDF only, each file under 10 MB
- `Upload Pre Alert File`: `.xls` or `.xlsx`, under 20 MB

Excel validation uses the new Pre Alert template:

- Row 1 is treated as headers; validation starts at row 2.
- L column (`name`) is the recipient.
- M column (`thoroughfare`) is the address.
- W column (`price`) is the declared amount.
- For the same recipient and address, the total declared amount must not exceed `150 EUR`.
- A non-empty W value must be numeric.
- If W has an amount, L and M are required.
- Other business validation rules are intentionally not active yet.

Successful uploads are stored with status `pending_review`. Admins can later mark them `approved` or `rejected`.

## API

- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/users`, admin only
- `POST /api/v1/users`, admin only
- `PATCH /api/v1/users/{userId}`, admin only
- `POST /api/v1/users/{userId}/reset-password`, admin only
- `GET /api/v1/waybill-uploads`
- `POST /api/v1/waybill-uploads/file`
- `POST /api/v1/waybill-uploads/pre-alert`
- `PATCH /api/v1/waybill-uploads/{uploadId}/status`, admin only
- `GET /api/v1/waybill-uploads/{uploadId}/files/{fileId}/download`
- `DELETE /api/v1/waybill-uploads/{uploadId}`

## Ubuntu 24.04 Deployment Notes

Install runtime dependencies:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip postgresql postgresql-contrib
```

Initialize PostgreSQL:

```bash
sudo -u postgres psql
CREATE DATABASE omniship_poc;
CREATE USER omniship_user WITH PASSWORD 'change_me';
GRANT ALL PRIVILEGES ON DATABASE omniship_poc TO omniship_user;
\q
```

Backend:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m alembic upgrade head
python -m app.cli create-admin
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run build
npm run start -- --host 0.0.0.0 --port 3000
```

Set `AUTH_COOKIE_SECURE=true` when serving over HTTPS in production.

## Tests

Backend:

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

Frontend:

```powershell
cd frontend
npm test -- --run
npm run lint
npm run build
```

Alembic SQL dry run:

```powershell
cd backend
..\.venv\Scripts\python -m alembic upgrade head --sql
```
