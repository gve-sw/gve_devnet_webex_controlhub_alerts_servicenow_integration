FROM python:3.12-slim

WORKDIR /app
COPY ./requirements.txt /app
RUN pip install -r requirements.txt

COPY ./src .

EXPOSE 5000
CMD ["python", "./app.py"]
