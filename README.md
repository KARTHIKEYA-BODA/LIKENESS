# Likeness

**A clothing store with visual product search.**

Likeness combines a lightweight web storefront with a FastAPI backend. It uses Supabase Postgres for application data and `pgvector` for image embeddings.

## What’s inside

- **Storefront:** browse products, manage a cart, and place orders.
- **Visual search:** find products using image embeddings powered by CLIP.
- **API:** FastAPI endpoints for authentication, catalog, cart, orders, and admin tasks.
- **Database:** Supabase Postgres schema and migrations.
- **Sign-in:** email/password authentication and optional Google sign-in through Supabase.

## Requirements

- Python 3.10 or newer
- A [Supabase](https://supabase.com/) project
- [Git](https://git-scm.com/) (to clone the project)

## Get started

### 1. Set up the database

1. Create a Supabase project.
2. Open **SQL Editor**, run [`db/schema.sql`](db/schema.sql), and wait for it to finish. This enables `pgvector` and creates the tables, indexes, triggers, and views.
3. In the Supabase project’s **Connect** panel, copy the PostgreSQL connection URI. For a deployed API, use the **Session pooler** URI and keep `?sslmode=require`.

If you already applied an earlier version of the schema, run [`db/migrations/001_supabase_google_auth.sql`](db/migrations/001_supabase_google_auth.sql) to add Google-auth support.

### 2. Configure the backend

Create `backend/.env` and add your settings:

```env
DATABASE_URL=postgresql://...
JWT_SECRET=replace-with-a-random-secret-at-least-32-characters-long

# Optional: enable Google sign-in through Supabase
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_OR_PUBLISHABLE_KEY

# Optional: add the origin of your frontend when it is not localhost:5173
FRONTEND_URLS=http://localhost:5173
```

Keep `backend/.env` private and never commit it. The API requires `DATABASE_URL` and a `JWT_SECRET` of at least 32 characters to start.

### 3. Install dependencies and start the API

In PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://127.0.0.1:8000`. Check the database connection at [`http://127.0.0.1:8000/api/health`](http://127.0.0.1:8000/api/health); a healthy response includes `"database": "connected"`.

### 4. Start the storefront

In a second terminal, from the project root, run:

```powershell
py -3 -m http.server 5173
```

Then open [`http://localhost:5173`](http://localhost:5173). You can also run `start-likeness.bat` from the project root to start the storefront server.

## Enable Google sign-in

1. In **Supabase Dashboard → Authentication → Providers → Google**, enable Google and enter your OAuth client ID and secret.
2. In **Authentication → URL Configuration**, add the storefront URL to the redirect allow-list, such as `http://localhost:5173/*` for local development. OAuth does not work from a `file://` URL.
3. Copy [`supabase-config.example.js`](supabase-config.example.js) to `supabase-config.js` and set your Supabase project URL and anon/publishable key.
4. Set the same `SUPABASE_URL` and `SUPABASE_ANON_KEY` values in `backend/.env`.

The browser anon/publishable key is intended to be public. Never put a database password or Supabase service-role key in `supabase-config.js`.

## Optional: add demo data

With the database schema installed and the backend environment configured, run:

```powershell
cd backend
python seed.py
```

The seed script generates sample images and downloads the CLIP model on first use (approximately 600 MB). It creates these development accounts:

- Admin: `admin@likeness.dev` / `admin123`
- Shopper: `shopper@likeness.dev` / `shopper123`

These are for local development only. Change or remove them before publishing.

## Deployment notes

- Set `DATABASE_URL` and a unique `JWT_SECRET` (at least 32 characters) in your deployment environment.
- Set `FRONTEND_URLS` to the deployed storefront origin or origins, separated by commas.
- Product images are stored in `backend/uploads`. Use object storage, such as Supabase Storage, before deploying to serverless or multiple API instances.
- This backend connects to Postgres server-side and enforces authorization in FastAPI. Apply row-level security if clients will connect directly to Supabase.
