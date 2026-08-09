# Natural Language Analytics System

A Django and React analytics application backed by PostgreSQL. It provides
predefined dashboards, safe natural-language database queries, charts, and
trend projections.

## Local development

Create and activate a virtual environment, then install the Python packages:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start Django from this directory:

```powershell
python manage.py runserver 8000
```

In a second terminal, start React:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` requests to Django on port
8000.

## Production build

Build React and collect its assets for Django/WhiteNoise:

```powershell
cd frontend
npm ci
npm run build
cd ..
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Run the combined application on Windows with Waitress:

```powershell
waitress-serve --listen=0.0.0.0:8000 member_analytics_project.wsgi:application
```

On Linux, the same WSGI entry point can be hosted with Gunicorn, uWSGI, or the
supervisor's existing Django server setup.

Required production settings include:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=analytics.example.com,10.0.0.20
CORS_ORIGINS=https://analytics.example.com
```

When Django serves the React build from the same hostname, `CORS_ORIGINS` is
not required by the browser but may remain configured.

## Database and AI configuration

Update `.env` with the PostgreSQL credentials, table/column names, and an Azure
OpenAI, Groq, OpenAI, GitHub Models, or Ollama configuration. The analytics
queries continue to use SQLAlchemy directly; Django's small SQLite database is
only available for Django internals and does not contain analytics data.

The default member table contains `status`, `amount`, `target_amount`,
`network`, `channel`, `created_at`, and `product_code`. All names and status
values can be configured in `.env`. Generated target-amount analytics exclude
invalid text and per-account targets above `MAX_TARGET_AMOUNT`, which defaults
to 10,000,000,000.

## API endpoints

- `GET /api/health`
- `GET /api/dashboard`
- `GET /api/benefits`
- `GET /api/questions?domain=enrolments|benefits`
- `POST /api/ask`

All existing React API contracts are preserved by the Django migration.

## Legacy Streamlit interface

The earlier Streamlit interface remains available during the transition:

```powershell
streamlit run app.py
```
