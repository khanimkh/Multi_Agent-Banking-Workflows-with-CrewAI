# Multi-Agent Banking Workflows with CrewAI

This is a standalone CrewAI project:

- YAML-driven agent and task configuration.
- Data analysis and reporting workflow design.
- Multi-crew and sales-flow architecture.
- Production-style runnable script and setup.

## Project Structure

```text
Bank-Assistant-CrewAI/
  .gitignore
  pyproject.toml
  README.md
  src/
    bank_assistant_crew/
      __init__.py
      __main__.py
      main.py
      crew.py
      models.py
      sales_flow.py
      flow_kickoff.py
      content_pipeline.py
      tools/
        __init__.py
        custom_tool.py
      config/
        agents.yaml
        tasks.yaml
        risk_compliance_agents.yaml
        risk_compliance_tasks.yaml
        bank_lead_qualification_agents.yaml
        bank_lead_qualification_tasks.yaml
        bank_email_engagement_agents.yaml
        bank_email_engagement_tasks.yaml
        bank_content_agents.yaml
        bank_content_tasks.yaml
  data/
    customers.csv
    transactions.csv
    support_tickets.csv
  reports/
    .gitkeep
  requirements.txt
```

## What This Project Does

The project provides banking workflow orchestration with two coordinated CrewAI workflows:

1. Advisory and Service Workflow
- Customer profiling and intent understanding
- Product recommendation (cards, loans, savings)
- Service action planning and follow-up communication

2. Risk and Compliance Workflow
- Transaction risk review and fraud signal checks
- Compliance validation based on region/risk level
- Final risk memo and guardrail recommendations

It also includes a project-3 style two-crew pipeline:

1. Bank Lead Qualification Crew
- Defined in `src/bank_assistant_crew/config/bank_lead_qualification_agents.yaml` and `src/bank_assistant_crew/config/bank_lead_qualification_tasks.yaml`
- Performs lead data collection, banking fit analysis, and lead scoring validation

2. Bank Email Engagement Crew
- Defined in `src/bank_assistant_crew/config/bank_email_engagement_agents.yaml` and `src/bank_assistant_crew/config/bank_email_engagement_tasks.yaml`
- Drafts and optimizes personalized customer follow-up emails

3. Bank Sales Flow + Flow Kickoff
- Flow class in `src/bank_assistant_crew/sales_flow.py` (SalesPipeline-like pattern with `@start` and `@listen`)
- Kickoff runner in `src/bank_assistant_crew/flow_kickoff.py`
- Produces `reports/bank_sales_flow_output.json`

4. Project-5 Style Multi-LLM Content Pipeline
- Script: `src/bank_assistant_crew/content_pipeline.py`
- Multi-LLM model routing per agent via environment variables
- Generates structured social posts and blog post outputs

## Web UI Executors

The frontend includes three workflow executors:

1. Customer Support and Advisory Executor
- Runs primary advisory and risk/compliance workflows for one customer

2. Sales Flow Executor
- Runs lead qualification, prioritization, and follow-up email generation flow

3. Content Pipeline Executor
- Generates blog and social content through multi-agent content workflow

## Create Pydantic Models for Structured Output

This project now includes a dedicated Pydantic schema module in `src/bank_assistant_crew/models.py`.

Structured output models include:
- `LeadQualificationOutput`
- `EmailEngagementOutput`
- `RiskComplianceOutput`
- `SocialMediaPost`
- `ContentOutput`

Where they are used:
- `src/bank_assistant_crew/crew.py`: attaches `output_pydantic` to lead scoring and email optimization tasks
- `src/bank_assistant_crew/content_pipeline.py`: uses `ContentOutput` for blog + social structured generation

Why this helps:
- Consistent machine-readable outputs across crews
- Easier validation and downstream automation
- Similar technique to the structured output workflow used in `CrewAI-project` lessons

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add environment variables in a `.env` file (for your selected model provider), e.g.:

```env
OPENAI_API_KEY=your_key_here
```

## Run

```bash
python -m bank_assistant_crew.main --customer-name "Alex Morgan" --customer-goal "reduce monthly credit card debt" --region "US" --risk-level "medium"
```

Run the project-3 style flow kickoff:

```bash
python -m bank_assistant_crew.flow_kickoff
```

Run the project-5 style content pipeline:

```bash
python -m bank_assistant_crew.content_pipeline --subject "AI-powered debt management" --region "US"
```

Output is written to:

- `reports/bank_assistant_summary.md`
- `reports/bank_sales_flow_output.json`
- `reports/bank_blog_post.md`
- `reports/bank_social_posts.md`
- `reports/bank_content_output.json`

These files are created automatically at runtime during successful workflow execution.

## Notes

- The sample CSVs in `data/` are starter inputs to ground prompts and future tooling.

## Web App and Docker

This project now includes a backend API and a frontend web UI while preserving all existing CrewAI techniques.

Added components:
- Backend API: `src/bank_assistant_crew/api.py` (FastAPI)
- Frontend UI: `frontend/` (HTML/CSS/JS served by FastAPI)
- Docker files: `Dockerfile`, `docker-compose.yml`

Important:
- Existing techniques are kept intact (multi-crew, flow kickoff, multi-LLM content, tools, and Pydantic structured outputs).
- Even if not all internals are visualized in frontend, they are still executed through backend endpoints and still runnable from CLI modules.

Run locally (without Docker):

```bash
uvicorn bank_assistant_crew.api:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in a browser.

Run with Docker Compose:

```bash
docker compose up --build
```

Development note:
- `docker-compose.yml` mounts `src/`, `frontend/`, `reports/`, and `data/` so code and UI changes are picked up without rebuilding the image.

Endpoints/UI:
- Single app URL: `http://localhost:8000`

Key API routes:
- `POST /run/primary`
- `POST /run/flow`
- `POST /run/content`
- `GET /reports`
