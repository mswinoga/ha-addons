ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Install requirements for add-on
#RUN apk add --no-cache python3
#RUN pip3 install --upgrade pip
RUN pip3 install pymodbus paho-mqtt

# Python 3 HTTP Server serves the current working dir
# So let's set it to our add-on persistent data directory.
WORKDIR /data

# Copy data for add-on
COPY run.sh /
COPY gateway /gateway
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
