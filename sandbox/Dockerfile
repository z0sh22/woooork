# Resolve/pin this base to a reviewed digest before collecting research results.
FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b
LABEL org.safety-games.runner="1"
COPY --chmod=0555 execute.py /opt/sandbox/execute.py
COPY --chmod=0555 tool.py /opt/sandbox/tool.py
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/python", "-I", "-B", "/opt/sandbox/execute.py"]
