# app/Dockerfile

FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

#RUN pip install -r requirements.txt
COPY . .

RUN pip install --upgrade pip && pip install -r requirements.txt

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "🏚️Home.py", "--server.port=8501", "--server.address=0.0.0.0"]

