FROM python:3.13-slim

WORKDIR /app

# Copied on its own so a code change doesn't reinstall the dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The database lives here - mount it as a volume so results survive a rebuild.
VOLUME /app/data
ENV DWTS_DB=/app/data/league.db

ENV DWTS_PORT=8000
EXPOSE 8000

# One worker on purpose: plenty for a three-person league, and it keeps a
# single process talking to the SQLite file. Shell form so DWTS_PORT expands;
# exec so gunicorn stays PID 1 and still gets your stop signals.
CMD exec gunicorn -w 1 -b 0.0.0.0:${DWTS_PORT} app:app
