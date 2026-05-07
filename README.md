# Bank Assistant CrewAI

A production-ready multi-agent AI system built with [CrewAI](https://docs.crewai.com) that
orchestrates five distinct banking workflows — from customer advisory and risk compliance,
through lead qualification and email engagement, to AI-generated content — all accessible
via a live web application and REST API.

---

## Features

- **5 independent CrewAI workflows** driven entirely by YAML configuration
- **Multi-LLM routing** — assign a different OpenAI model to each agent via environment variables
- **Pydantic structured outputs** — enforce machine-readable JSON from every crew
- **CrewAI Flow** — event-driven sales pipeline with `@start` / `@listen` decorators
- **Custom tools** — agents read real CSV data (customers, transactions, support tickets) and live banking trend signals
- **Background job API** — long-running workflows run in daemon threads; the UI polls for live log output
- **FastAPI + Docker** — single-container deployment with volume-mounted source for live code updates

---

## Agents

| Agent | Workflow | Responsibility |
|---|---|---|
| `customer_profile_agent` | Advisory | Profiles the customer's financial goals and history |
| `product_recommendation_agent` | Advisory | Recommends suitable banking products |
| `service_action_agent` | Advisory | Plans follow-up actions and communications |
| `risk_assessment_agent` | Risk & Compliance | Reviews transactions for fraud and risk signals |
| `compliance_validation_agent` | Risk & Compliance | Validates against regulatory requirements |
| `risk_reporting_agent` | Risk & Compliance | Produces the final risk memo |
| `lead_data_agent` | Lead Qualification | Fetches and enriches raw lead data from CSV |
| `banking_fit_agent` | Lead Qualification | Scores product–customer fit |
| `lead_scoring_agent` | Lead Qualification | Validates and outputs the final lead score |
| `personalization_agent` | Email Engagement | Drafts a personalised outreach email |
| `copywriting_agent` | Email Engagement | Optimises tone, CTA, and messaging |
| `market_trends_agent` | Content Pipeline | Researches banking trends (uses `BankingTrendSignalTool`) |
| `audience_insights_agent` | Content Pipeline | Analyses audience opportunities by region |
| `content_creator_agent` | Content Pipeline | Writes blog post and social media posts |
| `quality_assurance_agent` | Content Pipeline | Reviews and refines the final content output |

---

## Project Structure

```text
Bank-Assistant-CrewAI/
├── .env                          # OPENAI_API_KEY and model overrides (not committed)
├── docker-compose.yml            # Service definition with volume mounts
├── Dockerfile                    # python:3.11-slim, installs deps, runs uvicorn on port 8000
├── requirements.txt              # All Python dependencies
├── pyproject.toml                # Package metadata
│
├── data/
│   ├── customers.csv             # Customer profile records
│   ├── transactions.csv          # Transaction history records
│   └── support_tickets.csv       # Customer support ticket records
│
├── frontend/
│   ├── index.html                # Single-page web UI
│   ├── app.js                    # Fetch API calls, job polling, result rendering
│   └── style.css                 # Styling
│
├── reports/                      # All workflow outputs written here at runtime
│   ├── bank_assistant_summary.md
│   ├── bank_sales_flow_output.json
│   ├── bank_blog_post.md
│   ├── bank_social_posts.md
│   └── bank_content_output.json
│
└── src/
    └── bank_assistant_crew/
        ├── __init__.py
        ├── __main__.py           # Allows: python -m bank_assistant_crew
        ├── main.py               # CLI entry point for primary workflows
        ├── api.py                # FastAPI backend — all endpoints + job management
        ├── crew.py               # Builds Crew, Agents, Tasks from YAML
        ├── models.py             # Pydantic output models for structured results
        ├── sales_flow.py         # BankSalesFlow — CrewAI Flow with @start/@listen
        ├── flow_kickoff.py       # Async runner for BankSalesFlow
        ├── content_pipeline.py   # Multi-LLM content generation pipeline
        │
        ├── config/
        │   ├── agents.yaml                        # Advisory workflow agents
        │   ├── tasks.yaml                         # Advisory workflow tasks
        │   ├── risk_compliance_agents.yaml        # Risk & compliance agents
        │   ├── risk_compliance_tasks.yaml         # Risk & compliance tasks
        │   ├── bank_lead_qualification_agents.yaml
        │   ├── bank_lead_qualification_tasks.yaml
        │   ├── bank_email_engagement_agents.yaml
        │   ├── bank_email_engagement_tasks.yaml
        │   ├── bank_content_agents.yaml
        │   └── bank_content_tasks.yaml
        │
        └── tools/
            ├── __init__.py
            └── custom_tool.py    # CustomerDataFetcherTool, TransactionDataFetcherTool,
                                  # SupportTicketFetcherTool, BankingTrendSignalTool
```

---

## Workflows

### 1 — Customer Advisory and Service
Uses `agents.yaml` + `tasks.yaml`. Three agents work sequentially to profile the
customer, recommend products, and plan service actions.

### 2 — Risk and Compliance Validation
Uses `risk_compliance_agents.yaml` + `risk_compliance_tasks.yaml`. Assesses transaction
risk, validates compliance rules by region, and produces a risk memo.

### 3 — Lead Qualification Crew
Uses `bank_lead_qualification_agents.yaml` + `bank_lead_qualification_tasks.yaml`.
Fetches lead data via `CustomerDataFetcherTool`, scores product fit, and outputs a
validated `LeadQualificationOutput` Pydantic object.

### 4 — Email Engagement Crew
Uses `bank_email_engagement_agents.yaml` + `bank_email_engagement_tasks.yaml`.
Takes a qualified lead and writes a personalised email with subject line, body, and
CTA — validated as `EmailEngagementOutput`.

### 5 — Multi-LLM Content Pipeline
Uses `bank_content_agents.yaml` + `bank_content_tasks.yaml`. Four agents each run on
a configurable LLM model to produce a blog post and platform-specific social posts —
validated as `ContentOutput`.

### BankSalesFlow (CrewAI Flow)
An event-driven pipeline in `sales_flow.py` that chains Workflows 3 and 4 automatically:

```
fetch_leads → score_leads → ┬→ store_leads_score
                            └→ filter_leads (score ≥ 70) → write_email → send_email
```

---

## Pydantic Structured Output Models

Defined in `models.py` and attached to tasks via `output_pydantic`:

| Model | Used in | Fields |
|---|---|---|
| `LeadQualificationOutput` | Lead Qualification | `customer_name`, `lead_score`, `fit_score`, `recommended_path`, `risk_notes` |
| `EmailEngagementOutput` | Email Engagement | `subject_line`, `email_body`, `primary_cta` |
| `RiskComplianceOutput` | Risk & Compliance | `risk_level`, `top_risks`, `controls`, `escalation_required` |
| `SocialMediaPost` | Content Pipeline | `platform`, `content` |
| `ContentOutput` | Content Pipeline | `blog_post`, `social_media_posts` |

---

## Setup

### Prerequisites
- Python 3.11+
- Docker Desktop (for Docker-based run)
- An OpenAI API key

### Step 1 — Create `.env`

```env
OPENAI_API_KEY=sk-proj-your-key-here

# Optional: override the LLM per agent in the content pipeline
OPENAI_MODEL_NAME=gpt-4o-mini
BANK_MARKET_LLM=gpt-4o-mini
BANK_STRATEGY_LLM=gpt-4o-mini
BANK_CREATOR_LLM=gpt-4o-mini
BANK_QA_LLM=gpt-4o-mini
BANK_ALT_LLM=gpt-4o-mini
```

### Step 2 — Install dependencies (local Python only)

```bash
pip install -r requirements.txt
```

---

## Run

### Docker (recommended)

```bash
docker compose up --build -d
```

Open the web UI: `http://localhost:8000`

Stop:

```bash
docker compose down
```

Check logs:

```bash
docker compose logs -f app
```

### Local Python

Start the API server:

```bash
uvicorn bank_assistant_crew.api:app --host 0.0.0.0 --port 8000
```

Run primary workflows from CLI:

```bash
python -m bank_assistant_crew.main \
  --customer-name "Alex Morgan" \
  --customer-goal "reduce monthly credit card debt" \
  --region "US" \
  --risk-level "medium"
```

Run the sales flow from CLI:

```bash
python -m bank_assistant_crew.flow_kickoff
```

Run the content pipeline from CLI:

```bash
python -m bank_assistant_crew.content_pipeline \
  --subject "AI-powered debt management" \
  --region "US"
```

---

## CLI Arguments

### `main.py`

| Argument | Type | Default | Description |
|---|---|---|---|
| `--customer-name` | str | `"Alex Morgan"` | Full name of the customer |
| `--customer-goal` | str | `"reduce monthly credit card debt"` | Customer's financial goal |
| `--region` | str | `"US"` | Geographic region (affects compliance logic) |
| `--risk-level` | str | `"medium"` | Initial risk classification hint |

### `content_pipeline.py`

| Argument | Type | Default | Description |
|---|---|---|---|
| `--subject` | str | `"responsible use of AI agents in retail banking"` | Content topic |
| `--region` | str | `"US"` | Region for market trend research |

---

## API Endpoints

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `GET` | `/` | Serves `frontend/index.html` |
| `GET` | `/app.js` | Serves frontend JavaScript |
| `GET` | `/style.css` | Serves frontend stylesheet |
| `POST` | `/run/primary` | Runs advisory + risk workflows synchronously |
| `POST` | `/jobs/primary` | Enqueues advisory + risk workflows as a background job |
| `GET` | `/jobs/{job_id}` | Polls a background job for status and live log output |
| `POST` | `/run/content` | Runs the content pipeline synchronously |
| `POST` | `/run/flow` | Runs the BankSalesFlow asynchronously |
| `GET` | `/reports` | Lists all files in the `reports/` directory |

### Request bodies

**`POST /run/primary` and `POST /jobs/primary`**
```json
{
  "customer_name": "Alex Morgan",
  "customer_goal": "reduce monthly credit card debt",
  "region": "US",
  "risk_level": "medium"
}
```

**`POST /run/content`**
```json
{
  "subject": "responsible use of AI agents in retail banking",
  "region": "US"
}
```

**`POST /run/flow`** — no request body required.

---

## Output Files

All files are written to the `reports/` directory:

| File | Written by | Contents |
|---|---|---|
| `bank_assistant_summary.md` | `main.py` / `/run/primary` | Combined advisory + risk workflow Markdown report |
| `bank_sales_flow_output.json` | `sales_flow.py` | Scored leads, high-priority leads, drafted emails |
| `bank_blog_post.md` | `content_pipeline.py` | Long-form blog post in Markdown |
| `bank_social_posts.md` | `content_pipeline.py` | Platform-specific social posts |
| `bank_content_output.json` | `content_pipeline.py` | Structured JSON with blog + social post data |

---

## Custom Tools

| Tool | Assigned to | Data source |
|---|---|---|
| `CustomerDataFetcherTool` | `lead_data_agent` | `data/customers.csv` |
| `TransactionDataFetcherTool` | `lead_data_agent` | `data/transactions.csv` |
| `SupportTicketFetcherTool` | `lead_data_agent` | `data/support_tickets.csv` |
| `BankingTrendSignalTool` | `market_trends_agent` | Hardcoded regional signals + topic injection |

---

## Docker Details

The `docker-compose.yml` mounts four directories as live volumes so changes take
effect immediately after a container restart — no rebuild needed for source code
or frontend updates:

```yaml
volumes:
  - ./src:/app/src
  - ./frontend:/app/frontend
  - ./reports:/app/reports
  - ./data:/app/data
```

To apply Python code changes inside a running container:

```bash
docker compose restart app
```

To apply `docker-compose.yml` or `Dockerfile` changes:

```bash
docker compose up --build -d
```
- `GET /reports`
