# Natural Language Analytics System

A presentation-ready Streamlit MVP with a PostgreSQL analytics dashboard and a
read-only natural-language database agent.

The natural-language interface can also return end-user-friendly charts and
trend projections. Projection questions fetch historical monthly data with
read-only SQL, then calculate future values in Python using a recent linear
trend.

## Quick start

### FastAPI and React

Install the Python dependencies, then start the API from this directory:

```powershell
pip install -r requirements.txt
uvicorn api:app --reload
```

In a second terminal, start the React application:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Interactive API documentation is available at
`http://localhost:8000/docs`. For production, set `CORS_ORIGINS` to a
comma-separated list of allowed frontend origins.

### Legacy Streamlit interface

1. Open a terminal in this folder.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

4. Update `.env` with the PostgreSQL credentials, real table/column names, and
   an Azure OpenAI, Groq, OpenAI, GitHub Models, or Ollama configuration.
   For Azure OpenAI, set `LLM_PROVIDER=azure` and provide
   `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
   `AZURE_OPENAI_API_VERSION`, and `AZURE_OPENAI_CHAT_DEPLOYMENT`.
   For Groq, paste the key into `GROQ_API_KEY` and keep `LLM_PROVIDER=groq`.
   For GitHub Models, paste the PAT into `GITHUB_TOKEN` and keep
   `LLM_PROVIDER=github`.
5. Start the application:

   ```powershell
   streamlit run app.py
   ```

## Expected database fields

The defaults target a `member_accounts` table containing `status`, `amount`,
`target_amount`, `network`, `channel`, `created_at`, and `product_code`. Every
name and status value can be changed in `.env` to match an existing database.
Generated target-amount analytics exclude invalid text and per-account targets
above `MAX_TARGET_AMOUNT`, which defaults to 10,000,000,000.

## Demo checklist

- Confirm the sidebar says **Database connected**.
- Open the dashboard and explain the five metrics and four visualizations.
- Open **Ask Database** and run two prepared questions.
- Ask for a six-month registration projection and explain the historical versus
  projected lines and the estimate disclaimer.
- Expand the generated SQL and result table while explaining the read-only guard.
- Finish on **About** to show the system architecture.

## Presenter summary

> The system has two components. The first is an analytical engine that
> generates predefined metrics and visualizations from PostgreSQL. The second is
> an AI-powered natural-language interface that translates questions into safe,
> read-only SQL, executes them, and returns both the results and a human-readable
> explanation through the same Streamlit application.
