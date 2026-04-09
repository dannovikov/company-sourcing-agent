FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application code
COPY . .

# Create data directory for SQLite default
RUN mkdir -p /app/data

# Run database migrations then start the server
EXPOSE 8080
CMD ["sh", "-c", "python -c 'from src.db.session import init_db; init_db()' && uvicorn src.dashboard.app:create_app --factory --host 0.0.0.0 --port 8080"]
