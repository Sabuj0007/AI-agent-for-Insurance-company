# Use an official Python runtime
FROM python:3.10-slim

# avoid interactive prompts during package installs
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# install system deps needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# create app directory
WORKDIR /app

# copy requirements first (leverages Docker cache)
COPY requirements.txt .

# upgrade pip and install requirements
RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# copy app source
COPY . .

# expose port used by uvicorn
EXPOSE 8000

# default command (dev friendly). Remove --reload in production.
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
