FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
COPY frontend ./frontend
COPY data ./data
COPY reports ./reports

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "bank_assistant_crew.api:app", "--host", "0.0.0.0", "--port", "8000"]
