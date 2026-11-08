FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24

WORKDIR /opt/behaelterverwaltung

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
