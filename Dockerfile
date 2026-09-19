FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir Flask gunicorn

COPY . .

# The database lives here - mount it as a volume so results survive a rebuild.
VOLUME /app/data
ENV DWTS_DB=/app/data/league.db

EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
