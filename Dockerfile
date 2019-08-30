FROM python:3.7
MAINTAINER Philip Ahlberg "philip.ahlberg@sesam.io"

WORKDIR /service
ADD ./requirements.txt /service/requirements.txt
RUN pip install -r requirements.txt

ADD . /service

EXPOSE 5000/tcp

CMD ["python3", "-u", "./service/o365graph.py"]
