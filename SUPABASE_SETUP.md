# Voyayaha curated places database — Supabase setup

This database is a SECONDARY source for Hidden Places. The current Reddit + YouTube discovery remains first priority. The backend uses Supabase only to fill missing recommendation slots or when social evidence is insufficient.

## 1. Create the free Supabase project

Create a project at https://supabase.com. The current Free plan includes a 500 MB Postgres database and 1 GB file storage.

## 2. Create the table

Open **SQL Editor** and run the SQL in `supabase_schema.sql`.

## 3. Add your places

Open **Table Editor → voyayaha_places → Insert row**. Start with 20–50 genuinely useful places. Set `verified=true` and `published=true` only after you have checked the place.

Minimum fields to enter: `name`, `city`, `country`, `latitude`, `longitude`, `category`, `description`, `best_for`.

## 4. Connect Render

In Render → your backend service → Environment add:

```
SUPABASE_URL=https://YOUR-PROJECT-REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_PLACES_TABLE=voyayaha_places
```

Get the URL and service-role key from **Supabase → Project Settings → API**.

**Important:** the service-role key must exist ONLY in Render. Do not put it in Cloudflare, Vite `.env`, GitHub, or frontend code.

## 5. Deploy the backend

After deployment, open:

`https://YOUR-RENDER-URL/database/health`

You want `reachable: true`.

Then test:

`https://YOUR-RENDER-URL/database/places?location=Boston&query=peaceful%20places&radius_km=100&limit=3`

## 6. Hidden Places priority

The final recommendation order is:

1. Reddit + YouTube verified discovery (current working system).
2. Voyayaha curated Supabase places to fill remaining slots.

So if social discovery finds two strong places, the database supplies the third. If social discovery finds none, the database can supply up to three.
