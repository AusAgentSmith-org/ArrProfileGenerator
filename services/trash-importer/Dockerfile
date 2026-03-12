FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

RUN pip install --no-cache-dir requests

COPY services/trash-importer/src/ /app/src/

CMD ["python", "/app/src/main.py"]
