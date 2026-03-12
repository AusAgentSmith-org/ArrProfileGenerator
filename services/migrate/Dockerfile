FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/migrate/migrate.py /app/migrate.py

CMD ["python", "migrate.py"]
