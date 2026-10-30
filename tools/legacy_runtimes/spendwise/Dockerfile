FROM python:3.12-alpine

RUN addgroup -g 65534 -S nogroup && \
    adduser -u 65534 -S -G nogroup -s /sbin/nologin -D nobody

WORKDIR /app
COPY adapter.py /adapter.py

USER 65534:65534

ENTRYPOINT ["python", "/adapter.py"]

