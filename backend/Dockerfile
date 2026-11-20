FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
# Run as an unprivileged user
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
# Migrations run automatically on start (RUN_MIGRATIONS=true). --proxy-headers lets rate limiting see real client IPs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
