# Use the official lightweight Python image
FROM python:3.9-slim

# 1. Install System Dependencies (Graphviz is needed for the map!)
RUN apt-get update && apt-get install -y \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

# 2. Set the working directory
WORKDIR /app

# 3. Copy dependencies and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy the rest of the app code
COPY . .

# 5. Expose the port Streamlit runs on
EXPOSE 8080

# 6. Run the application
CMD ["streamlit", "run", "app.py", "--server.port=8080", "--server.address=0.0.0.0"]