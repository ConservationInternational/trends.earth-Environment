FROM osgeo/gdal:ubuntu-small-3.5.0
MAINTAINER Alex Zvoleff azvoleff@conservation.org

ENV USER script
USER root
RUN groupadd -r $USER && useradd -r -g $USER $USER

RUN apt-get update && \
    apt-get install -yq locales git python3-boto3 python3-pip \
        apt-transport-https ca-certificates wget gfortran python3-dev python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*  && \
    mkdir -p /project

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
