ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Install requirements for add-on
RUN apk add --no-cache py3-pip python3
RUN mkdir /venv && python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install pymodbus==2.5.3 paho-mqtt Unidecode

# Python 3 HTTP Server serves the current working dir
# So let's set it to our add-on persistent data directory.
WORKDIR /data

# Copy data for add-on
COPY run.sh /
COPY gateway /gateway
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
