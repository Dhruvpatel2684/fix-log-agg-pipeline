FROM python:3.11-slim

RUN pip install --no-cache-dir pytest

COPY runtime/ /app/runtime/

RUN mkdir -p /app/runtime/output

WORKDIR /app
