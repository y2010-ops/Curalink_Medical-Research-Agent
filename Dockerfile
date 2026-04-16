FROM python:3.10-slim

# Install Node.js
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean

WORKDIR /app

# Copy Python dependencies first for caching
COPY backend-python/requirements.txt ./backend-python/
RUN pip install --no-cache-dir -r backend-python/requirements.txt

# Copy Node dependencies
COPY backend-node/package*.json ./backend-node/
RUN cd backend-node && npm install

# Copy all project files
COPY backend-python/ ./backend-python/
COPY backend-node/ ./backend-node/

# Create a startup script
RUN echo '#!/bin/bash\n\
\n\
# Start Python API in the background\n\
cd /app/backend-python\n\
uvicorn server:app --host 127.0.0.1 --port 8000 &\n\
\n\
# Start Node Gateway in the foreground\n\
cd /app/backend-node\n\
export PORT=7860\n\
export PYTHON_API_URL="http://127.0.0.1:8000"\n\
npm start\n\
' > /app/start.sh

RUN chmod +x /app/start.sh

# Expose the port that Hugging Face Spaces expects
EXPOSE 7860

CMD ["/app/start.sh"]
