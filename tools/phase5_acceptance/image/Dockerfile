FROM golang:1.24.13-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac AS builder
WORKDIR /src
COPY . /src
RUN go mod download && CGO_ENABLED=0 go build -trimpath -buildvcs=false -o /app/main .

FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
ARG SOURCE_COMMIT
RUN apt-get update && apt-get -y full-upgrade && apt-get install -y --no-install-recommends ca-certificates postgresql python3 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/main /app/legacy
COPY adapter.py /go_fiber_adapter.py
COPY source-manifest.json /source-manifest.json
LABEL org.opencontainers.image.title="Rebase Go/Fiber characterization runtime" \
      org.opencontainers.image.version="go1.24.13-fiber-v1" \
      org.rebase.source.commit="${SOURCE_COMMIT}" \
      org.rebase.adapter="go-fiber-characterization-v1"
ENV PATH="/usr/lib/postgresql/16/bin:/usr/bin:/bin" PYTHONDONTWRITEBYTECODE=1 REBASE_SOURCE_COMMIT="${SOURCE_COMMIT}"
USER 65534:65534
WORKDIR /work
