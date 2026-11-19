# Waybill Pre Alert Upload Management

Internal EPIX back-office system for submitting and tracking Air Waybill Pre Alert data. Users upload a PDF Air Waybill document and an Excel Customer Pre Alert file; the backend validates the files, stores the upload locally, lets admins review submitted waybills, and exposes approved waybills on a tracking page.

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

Open [http://localhost:3000/](http://localhost:3000/). Unauthenticated users see the public EPIX landing page. Login is available at `/login`; successful login redirects to `/waybills`.

## Pages And Permissions

- `/` is the public EPIX landing page.
- `/login` is the only public login entry.
- `/waybills` shows approved waybill tracking records. Regular users only see their own records; admins see all records and can edit operational status/progress from the status badge.
- `/waybills/{publicCode}` shows the waybill detail shell for one approved record.
- `/waybill-uploads` lets admins and users upload Pre Alert data.
- `/waybill-upload-management` is admin-only and shows all submitted waybills.
- `/users` is admin-only account management.
- Regular users can upload and view only their own upload records.
- Admins can upload for a selected Target User, review all submissions, download attachments, approve/reject records, and delete local records.

Approved uploads automatically create a local tracking record with a unique 8-character public code. Tracking starts at `Created`; admins can update the operational status to `Created`, `NOA Received`, `Received`, `Ready To Scan`, `Scanning`, `Pending Clearance`, `Cleared`, `Partial Inbound`, `Inbound`, `Partial Outbound`, or `Outbound`.

## Upload Rules

Upload form fields:

- `Shipment Type`: `Air`, `Road`, or `Train`
- `Target User`: admin-only; regular users are always bound to their own account
- `Air Waybill Number`
- `Air Waybill Gross Weight (KG)`
- `Air Waybill Pieces`
- `Arrival Flight Number`, optional
- `Airport of Departure`
- `Airport of Arrival`
- `Air Waybill Document(s)`: PDF only, each file under 10 MB
- `Upload Pre Alert File`: temporarily unrestricted; file type, file size, and Excel content validation are currently bypassed

Excel validation is temporarily bypassed. When re-enabled, it uses the new Pre Alert template:

- Row 1 is treated as headers; validation starts at row 2.
- L column (`name`) is the recipient.
- M column (`thoroughfare`) is the address.
- W column (`price`) is the declared amount.
- For the same recipient and address, the total declared amount must not exceed `150 EUR`.
- A non-empty W value must be numeric.
- If W has an amount, L and M are required.
- U column value must be numeric when present and must be less than or equal to `5`.
- N, O, Q, and AC columns must be empty.
- A, B, C, D, E, F, and G column values must be consistent across all non-empty rows.
- Other business validation rules are intentionally not active yet.

Successful uploads are stored with review status `pending_review`. Admins can later mark them `approved` or `rejected`. Only `approved` uploads appear in `/waybills`.

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
- `GET /api/v1/waybills`
- `GET /api/v1/waybills/{publicCode}`
- `PATCH /api/v1/waybills/{publicCode}`, admin only

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

## AJ downstream tracking sync

Only administrators can assign an approved waybill to `AJ` from the Waybills list. AJ is queried by AWB. Status, airline record creation, airline arrival, AJ warehouse arrival, customs clearance, channel handover totals, final handover time, and POD files synchronize automatically. Each counter and milestone has an independent manual lock. Manual parcel edits lock parcel synchronization. Deleting an imported POD locks POD synchronization until an administrator unlocks it from the downstream dialog. Existing manual counters are protected by the migration.

Run `python -m alembic upgrade head` from `backend` before starting the updated backend and sync worker. Pause `epix-downstream-sync.timer` while deploying the migration, then enable it again. The downstream dialog shows the last result for every field. NOA, collection, scanning time, scanned/inbound/released quantities, and individual parcel states await additional AJ API data. See [the AJ field requirements](backend/AJ_SYNC_FIELD_REQUIREMENTS.md) for the agreed meanings and upstream data request.

The worker imports current vendor PODs and unassigned PODs using authenticated file downloads. File identity and version prevent duplicate downloads. Vendor updates replace superseded imported files after the database commit. Manual PODs retain their separate two-file limit. Imported files show their AJ source, vendor, version, and incomplete-document note.

Fill the ignored file `aj-credentials.env` in the project root:

```text
AJ_API_USERNAME=your_username
AJ_API_PASSWORD=your_password
```

Keep this file readable only by the backend service account. Test the account without changing a waybill using `cd backend` then `python -m app.cli test-aj --awb YOUR_KNOWN_AWB`. Run one sync with `python -m app.cli sync-downstream`. The worker queries each assigned waybill at most once per five-minute interval, defaults to a minimum of 0.5 seconds between shipment queries, and retains incidents for administrator review. New or changed PODs require additional authenticated download requests. `AJ_MIN_REQUEST_INTERVAL_SECONDS` adjusts the shipment query pace after AJ confirms its limit.

For Ubuntu systemd, copy `deploy/epix-downstream-sync.service` and `.timer` into `/etc/systemd/system/`. Replace `/srv/epix` and `User=epix` with the actual deployment directory and service account, ensure the backend virtual environment and root credential file are readable there, then run `systemctl daemon-reload` and `systemctl enable --now epix-downstream-sync.timer`. Check `systemctl status epix-downstream-sync.timer` and `journalctl -u epix-downstream-sync.service`. The PostgreSQL advisory lock prevents overlapping workers.

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
