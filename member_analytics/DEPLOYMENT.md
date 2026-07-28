# Streamlit Community Cloud deployment

The deployed app cannot connect to PostgreSQL on `localhost`. Move the table to
a hosted PostgreSQL provider first. The steps below use Neon.

## 1. Create the hosted database

1. Create a Neon project at <https://console.neon.tech>.
2. Open **Connect** and copy the direct, non-pooled connection string for the
   migration.

## 2. Export the local table

Run this from PowerShell. PostgreSQL will prompt for the local password.

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
  --host=localhost `
  --port=5432 `
  --username=postgres `
  --dbname=postgres `
  --format=custom `
  --table=public.member_accounts `
  --file=member_accounts.dump
```

## 3. Import into Neon

Replace the placeholder with the direct Neon connection string:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" `
  --verbose `
  --no-owner `
  --no-privileges `
  --dbname="<NEON_DIRECT_CONNECTION_STRING>" `
  member_accounts.dump
```

After the import, use Neon's SQL Editor to verify:

```sql
SELECT COUNT(*) FROM member_accounts;
```

The expected count is `229248`.

## 4. Deploy the app

1. Push the project to a GitHub repository. Do not commit `.env`.
2. Go to <https://share.streamlit.io> and select **Create app**.
3. Select the repository and branch.
4. Set the entrypoint to `member_analytics/app.py`.
5. Open **Advanced settings** and paste the secrets below.

```toml
DATABASE_URL = "<NEON_POOLED_CONNECTION_STRING>"
MEMBER_TABLE = "member_accounts"
STATUS_COLUMN = "status"
AMOUNT_COLUMN = "amount"
TARGET_AMOUNT_COLUMN = "target_amount"
MONETARY_COLUMNS = "amount,target_amount"
MAX_TARGET_AMOUNT = "10000000000"
NETWORK_COLUMN = "network"
CHANNEL_COLUMN = "channel"
CREATED_AT_COLUMN = "record_date"
PRODUCT_CODE_COLUMN = "product_code"
APPROVED_VALUE = "SUCCESS"
PENDING_VALUE = "PENDING"
REJECTED_VALUE = "FAILED"
LLM_PROVIDER = "groq"
GROQ_API_KEY = "<YOUR_GROQ_API_KEY>"
GROQ_MODEL = "llama-3.3-70b-versatile"
```

Use the pooled Neon connection string for the running web application. Keep all
passwords and API keys in Streamlit Secrets, not in GitHub.
