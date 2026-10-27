FROM python:3.12-alpine

WORKDIR /work

COPY legacy/ /work/legacy/
COPY tests/ /work/tests/
COPY schema.sql /work/schema.sql
COPY adapter.py /adapter.py

ENV PYTHONPATH=/work
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Non-root unprivileged nobody user
USER 65534:65534

CMD ["python", "/adapter.py"]
