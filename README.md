# Likeness

Likeness is a FastAPI clothing-store API with visual product search. It uses Supabase Postgres and the `pgvector` extension for image embeddings.

## Connect Supabase

1. Create a Supabase project.
2. Open **SQL Editor**, paste the contents of [`db/schema.sql`](db/schema.sql), and run it. This enables `pgvector` and creates all tables, indexes, triggers, and views.
3. In **Connect**, copy the Postgres connection URI. For a deployed API, choose the **Session pooler** connection string and retain `?sslmode=require`.
4. Copy `backend/.env.example` to `backend/.env`, then set `DATABASE_URL` and a unique `JWT_SECRET` of at least 32 characters. Do not commit this file.

## Google sign-in

1. Run [`db/migrations/001_supabase_google_auth.sql`](db/migrations/001_supabase_google_auth.sql) in Supabase SQL Editor if you had already applied the schema. New projects can simply use the updated [`db/schema.sql`](db/schema.sql).
2. In **Supabase Dashboard → Authentication → Providers → Google**, enable Google and enter your Google OAuth client ID and secret.
3. In **Authentication → URL Configuration**, add the actual URL where this page is served to the redirect allow-list, for example `http://localhost:5173/*` during development. Do not use `file://` for OAuth.
4. Copy `supabase-config.example.js` to `supabase-config.js`, then add your project URL and anon/publishable key. This browser key is designed to be public; never put your database password or service-role key in that file.
5. Set the same `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `backend/.env`.

The **Sign in** button then opens Google through Supabase. After sign-in, the FastAPI API verifies the Supabase session and adds or updates the account in the Supabase `users` table.

## Run the server

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Visit `http://127.0.0.1:8000/api/health`. A successful response includes `"database": "connected"`.

## Add demo data (optional)

After the schema is installed and the server environment is configured:

```powershell
cd backend
python seed.py
```

The seed process generates images and downloads the CLIP model on first use (roughly 600 MB). It creates two development accounts: `admin@likeness.dev` / `admin123` and `shopper@likeness.dev` / `shopper123`. Change or remove them before publishing.

## Deployment notes

- Supabase is used as the database; product image files are still written to `backend/uploads`. Use object storage (such as Supabase Storage) before deploying to serverless or multiple instances.
- Add the deployed frontend origin to `FRONTEND_URLS`, separated by commas if there is more than one origin.
- Apply row-level security only if clients will connect directly to Supabase. This backend uses its database connection server-side and enforces authorization in FastAPI.
