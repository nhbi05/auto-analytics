# Natural Language Analytics System

A presentation-ready Streamlit MVP with a PostgreSQL analytics dashboard and a
read-only natural-language database agent.

## Quick start

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
   a Groq, OpenAI, GitHub Models, or Ollama configuration.
   For Groq, paste the key into `GROQ_API_KEY` and keep `LLM_PROVIDER=groq`.
   For GitHub Models, paste the PAT into `GITHUB_TOKEN` and keep
   `LLM_PROVIDER=github`.
5. Start the application:

   ```powershell
   streamlit run app.py
   ```

## Expected database fields

The defaults target a `member_accounts` table containing `status`, `amount`,
`network`, `channel`, `created_at`, and `product_code`. Every name and status
value can be changed in `.env` to match an existing database.

## Demo checklist

- Confirm the sidebar says **Database connected**.
- Open the dashboard and explain the five metrics and four visualizations.
- Open **Ask Database** and run two prepared questions.
- Expand the generated SQL and result table while explaining the read-only guard.
- Finish on **About** to show the system architecture.

## Presenter summary

> The system has two components. The first is an analytical engine that
> generates predefined metrics and visualizations from PostgreSQL. The second is
> an AI-powered natural-language interface that translates questions into safe,
> read-only SQL, executes them, and returns both the results and a human-readable
> explanation through the same Streamlit application.
