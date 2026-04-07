FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/python-backend

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY python-backend /app/python-backend
COPY *.csv /app/
COPY *.json /app/

CMD ["python", "-m", "pipeline.runtime.run_stage1"]
