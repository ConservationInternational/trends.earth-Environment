FROM ghcr.io/osgeo/gdal:ubuntu-small-3.11.3
MAINTAINER Alex Zvoleff azvoleff@conservation.org

ENV USER script
USER root
RUN groupadd -r $USER && useradd -r -g $USER $USER

RUN apt-get update && \
    apt-get install -yq locales git \
        apt-transport-https ca-certificates wget gfortran \
        python3-dev python3-venv g++ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*  && \
    mkdir -p /project

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG en_US.UTF-8  ENV LANGUAGE en_US:en  ENV LC_ALL en_US.UTF-8

ADD requirements.txt /project/requirements-environment.txt
RUN pip install -r /project/requirements-environment.txt

COPY gefcore /project/gefcore
COPY main.py /project/main.py
COPY entrypoint.sh /project/entrypoint.sh

RUN chown $USER:$USER /project

WORKDIR /project

ENTRYPOINT ["./entrypoint.sh"]
