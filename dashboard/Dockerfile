# This Dockerfile is used to deploy a single-container Reflex app instance
# to services like Render, Railway, Heroku, GCP, and others.

# It uses a reverse proxy to serve the frontend statically and proxy to backend
# from a single exposed port, expecting TLS termination to be handled at the
# edge by the given platform.
FROM python:3.11-bookworm AS builder

WORKDIR /app

RUN pip install poetry
RUN apt-get -y update \
    && apt-get -y install --no-install-recommends libpq-dev gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*
# 
COPY dashboard/pyproject.toml dashboard/poetry.lock* /app/

RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# 
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copy the app locally for building 
COPY dashboard/ .
COPY ashared/supercog/ ./supercog/

ARG GOOGLE_CLIENT_ID
ARG S3_PUBLIC_BUCKET

ENV ENV=prod \
    DATABASE_URL="Placeholder" \
    GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID} \
    GOOGLE_CLIENT_SECRET="Placeholder"

# Deploy templates and prepare app
RUN reflex init

# Download all npm dependencies and compile frontend
RUN reflex export --frontend-only --no-zip && mv .web/_static/* /srv/ && rm -rf .web

COPY .git /tmp/.git

RUN cd /tmp && git rev-parse HEAD > /app/GIT_SHA


# This is the runtime image that will run the app.
# Files are copied from the builder image to the runtime image to reduce image size and avoid misc. cache.
FROM python:3.11-slim-bookworm AS runtime

# If the service expects a different port, provide it here (f.e Render expects port 10000)
ARG PORT=3000
# Only set for local/direct access. When TLS is used, the API_URL is assumed to be the same as the frontend.
ARG API_URL
ENV PORT=$PORT API_URL=${API_URL:-http://localhost:$PORT}

# Install Caddy server inside image
RUN apt-get update -y && apt-get install -y caddy curl unzip && rm -rf /var/lib/apt/lists/*

# Create /srv/usage directory and set permissions
RUN mkdir -p /srv/usage && chown -R caddy:caddy /srv

# Run as non-root user for better security and isolation
USER caddy

ENV LANG=C.UTF-8 \
    APP_HOME=/app \
    APP_USER=caddy \
    APP_GROUP=caddy

WORKDIR /app

# Create a simple Caddyfile to serve as reverse proxy
RUN cat > Caddyfile <<EOF
(cors) {
	@cors_preflight method OPTIONS
	@cors header Origin {args.0}

	handle @cors_preflight {
		header Access-Control-Allow-Origin "*"
		header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE"
		header Access-Control-Allow-Headers "DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range"
		header Access-Control-Max-Age "1728000"
		respond "" 204
	}

	handle @cors {
		header Access-Control-Allow-Origin "*"
		header Access-Control-Expose-Headers "Content-Length,Content-Range"
	}
}

http://supercog.ai:{\$PORT} {
	root * ${APP_HOME}/homepage
	file_server
}

http://app.supercog.ai:{\$PORT}, http://localhost:3000 {
	encode gzip

	@backend_routes path /_event/* /ping /_upload /_upload/* /signup_waitlist /slack/events
	handle @backend_routes {
		reverse_proxy localhost:8000
	}

    handle /email_handler* {
        reverse_proxy {\$TRIGGERSVC_URL}
    }

	root * /srv
	route {
		try_files {path} {path}/ /404.html
		file_server
	}

	handle_errors {
		@notfound expression {http.error.status_code} == 404
		header @notfound Location /
		respond @notfound "404 not found" 302
	}
}

http://engine.supercog.ai:{\$PORT} {
	import cors
	reverse_proxy {\$ENGINE_URL} {
		header_up X-Forwarded-Host {http.request.host}
		header_up X-Forwarded-Proto "https"
	}
}
EOF

# Copy the compiled frontend to the web root
COPY --from=builder --chown=${APP_USER}:${APP_GROUP} /srv/ /srv/

# Copy Python dependencies to the unpriveleged user home directory
COPY --from=builder --chown=${APP_USER}:${APP_GROUP} ${APP_HOME}/ .

ENV ENV=prod \
    PATH="${APP_HOME}/.venv/bin:$PATH"

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL

EXPOSE $PORT

# Apply migrations before starting the backend.
CMD [ -d alembic ] && reflex db migrate; \
    caddy start && reflex run --env prod --backend-only --loglevel info 
