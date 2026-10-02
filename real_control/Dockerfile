FROM python:3.12-slim
WORKDIR /app
COPY server.py test_server.py ./
RUN python -m unittest -v test_server.py
EXPOSE 8080
CMD ["python","-u","server.py"]
