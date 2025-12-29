FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir mkdocs mkdocs-material

COPY mkdocs.yml .
COPY docs/ docs/

EXPOSE 8000

CMD ["mkdocs", "serve", "--dev-addr=0.0.0.0:8000"]
