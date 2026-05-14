FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV EBF_PUBLIC_MODE=1
ENV EBF_REPORT_STORE=file:/data/reports

WORKDIR /app

COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt \
    && mkdir -p /data/reports

COPY projects ./projects
COPY README.md .

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn effective_boolean_filter.api:app --app-dir projects/effective_boolean_filter/src --host 0.0.0.0 --port ${PORT:-8000}"]
