# Only this already-local image supplies CPython; its application and env are excluded.
ARG LOCAL_RUNTIME
FROM ${LOCAL_RUNTIME} AS runtime
COPY prepare_runtime.py /phase6-prepare-runtime.py
RUN ["/usr/local/bin/python", "-I", "/phase6-prepare-runtime.py"]

FROM scratch
COPY --from=runtime /phase6-runtime/ /
COPY offline-tools/ /usr/local/lib/python3.12/site-packages/
COPY adapter.py /adapter.py
COPY scenarios.json /scenarios.json
COPY legacy_adapter.py /legacy_adapter.py
COPY legacy_calc.py /legacy/calc.py
COPY test_calc.py /acceptance/test_calc.py
COPY test_security.py /acceptance/test_security.py
ENV PATH=/usr/local/bin:/usr/bin:/bin
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
USER 65534:65534
WORKDIR /work
CMD ["python"]


