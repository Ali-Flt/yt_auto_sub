FROM python:3.13-slim
WORKDIR /app
COPY subs ./subs
ENV PYTHONUNBUFFERED=1 PORT=8765 CACHE_DIR=/cache
EXPOSE 8765
CMD ["python", "-m", "subs.app"]
