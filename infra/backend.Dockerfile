FROM python:3.13-slim AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.lock /app/backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock

FROM dependencies AS aws-validation
COPY backend/app /app/backend/app
COPY backend/fixtures/aws-validation /app/backend/fixtures/aws-validation
COPY scripts/validate_aws.py /app/scripts/validate_aws.py
USER 10001:10001
ENTRYPOINT ["python", "scripts/validate_aws.py"]
CMD ["--manifest", "backend/fixtures/aws-validation/manifest.json", "--region", "us-east-1", "--max-calls", "7"]

FROM dependencies AS runtime
COPY backend /app/backend
COPY frontend/public/demo /app/frontend/public/demo
RUN mkdir -p /app/data/storage && useradd -u 10001 -M app && chown -R app:app /app/data
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
