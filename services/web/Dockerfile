FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/shared

COPY services/web/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/web/src/ /app/src/

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
