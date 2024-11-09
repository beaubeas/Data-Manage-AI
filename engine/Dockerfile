
FROM python:3.11-bookworm as builder

WORKDIR /code

RUN pip install poetry
RUN apt-get update \
    && apt-get -y --no-install-recommends install libpq-dev gcc git \
    && rm -rf /var/lib/apt/lists/*
# 
COPY engine/pyproject.toml ./poetry.lock* ./

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

RUN python -m venv .venv

ENV PATH="/code/.venv/bin:$PATH"

# 
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY .git .git

RUN git rev-parse HEAD > GIT_SHA


FROM python:3.11-slim-bookworm as runtime

RUN apt-get update \
    && apt-get -y --no-install-recommends install git nmap mime-support \
    && rm -rf /var/lib/apt/lists/*

USER www-data
# 
ENV APP_HOME="/code" \
    APP_USER="www-data" \
    APP_GROUP="www-data"

WORKDIR /code

ENV PATH="/code/.venv/bin:$PATH"

# 
COPY --chown=${APP_USER}:${APP_GROUP} --from=builder /code/.venv /code/.venv
COPY --chown=${APP_USER}:${APP_GROUP} --from=builder /code/GIT_SHA ./GIT_SHA
COPY --chown=${APP_USER}:${APP_GROUP} --from=mwader/static-ffmpeg:7.0.2 /ffprobe /usr/local/bin/
# 

# 
COPY --chown=${APP_USER}:${APP_GROUP} engine/agents.sh ./agents.sh
COPY --chown=${APP_USER}:${APP_GROUP} engine/supercog ./supercog
COPY --chown=${APP_USER}:${APP_GROUP} engine/alembic ./alembic
COPY --chown=${APP_USER}:${APP_GROUP} engine/alembic.ini ./alembic.ini
COPY --chown=${APP_USER}:${APP_GROUP} engine/startup.sh ./startup.sh
COPY --chown=${APP_USER}:${APP_GROUP} ashared/supercog/ ./supercog/

RUN chmod +x ./startup.sh

ENV HOST="0.0.0.0"
ENV PORT="8080"

ENTRYPOINT ["/code/startup.sh"]

CMD uvicorn supercog.engine.main:app --host $HOST --port $PORT
