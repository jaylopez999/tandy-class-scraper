FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
EXPOSE 10000
CMD ["bash","-lc","gunicorn -k gevent -w 1 -t 120 -b 0.0.0.0:$PORT server:app"]
