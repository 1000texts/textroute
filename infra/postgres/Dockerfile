FROM postgres:17

RUN apt-get update && apt-get install -y --no-install-recommends \
   ca-certificates \
   postgresql-server-dev-17 \
   build-essential \
   git \
   && git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
   && cd /tmp/pgvector \
   && make \
   && make install \
   && rm -rf /tmp/pgvector \
   && apt-get remove -y build-essential git \
   && apt-get autoremove -y \
   && apt-get clean
