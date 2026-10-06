FROM python:3.11-slim

WORKDIR /app
COPY tools/active4x_persistence_w5.py /app/active4x_persistence_w5.py
COPY deploy/active4x-two-rivers/d2a/director_service.py /app/director_service.py
COPY deploy/active4x-two-rivers/d2a/director_ctl.py /app/director_ctl.py

VOLUME ["/state"]
CMD ["python", "/app/director_service.py"]
