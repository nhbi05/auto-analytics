# Django server deployment

This application is deployed as one Django WSGI service. Django exposes the API
and serves the compiled React interface through WhiteNoise.

## 1. Prepare the server

Install Python 3.11 or newer, Node.js 20 or newer, and PostgreSQL client tools.
Clone the repository, create a virtual environment, and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Configure secrets

Create `.env` on the server. Do not commit it. At minimum configure the
PostgreSQL connection, AI provider, and Django security values:

```dotenv
DATABASE_URL=postgresql://user:password@database-host:5432/database-name
MEMBER_TABLE=public.member_accounts
BENEFITS_TABLE=public.smartlife_contributions

DJANGO_SECRET_KEY=replace-with-a-long-random-value
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=analytics.example.com,10.0.0.20
CORS_ORIGINS=https://analytics.example.com

LLM_PROVIDER=groq
GROQ_API_KEY=replace-me
GROQ_MODEL=llama-3.3-70b-versatile
```

Retain the existing table, column, status, monetary-limit, and cache settings
from the development `.env`.

## 3. Build static files

```powershell
cd frontend
npm ci
npm run build
cd ..
python manage.py collectstatic --noinput
python manage.py check --deploy
```

Repeat these commands after frontend changes.

## 4. Start the WSGI service

For a Windows server:

```powershell
waitress-serve --listen=0.0.0.0:8000 member_analytics_project.wsgi:application
```

Configure the supervisor's service manager to run that command from the
`member_analytics` directory with the virtual environment active. Put IIS,
Nginx, or Apache in front of port 8000 for HTTPS and the public hostname.

For Linux, install the organization's preferred WSGI server and point it at:

```text
member_analytics_project.wsgi:application
```

## 5. Verify

```powershell
python manage.py check
```

Then open `/api/health` and confirm `database` is `true`, load the dashboard,
and submit one question through Ask the DB.

No Django migrations are required for analytics tables because the application
accesses the existing PostgreSQL schema through read-only SQLAlchemy queries.
