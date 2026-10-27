FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Avvio con porta dinamica ($PORT è iniettata da DigitalOcean App Platform).
# --proxy-headers --forwarded-allow-ips="*": dietro il load balancer di DO l'IP del client arriva da
# X-Forwarded-For (serve al freno dei tentativi di login per IP; vedi .agents/workflows/deploy.md).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
