FROM python:3-alpine
MAINTAINER Philip Ahlberg "philip.ahlberg@sesam.io"
COPY ./service /service

RUN pip install --upgrade pip

RUN pip install -r /service/requirements.txt

EXPOSE 5000/tcp

CMD ["python3", "-u", "./service/o365graph.py"]
