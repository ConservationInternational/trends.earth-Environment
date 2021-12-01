FROM continuumio/miniconda3
MAINTAINER Alex Zvoleff azvoleff@conservation.org

ENV USER script

USER root

RUN groupadd -r $USER && useradd -r -g $USER $USER

RUN apt-get update && apt-get -yq dist-upgrade		\
    && apt-get install -yq --no-install-recommends	\
    wget         					\
    gfortran						\
    gdal-bin						\
    libgdal-dev						\
    build-essential					\
    bzip2						\
    ca-certificates					\
    sudo						\
    locales						\
    ffmpeg \
    # ICU gives unicode libraries. Necessary for osgeo
    icu-devtools					\
    && apt-get clean                                    \
    && rm -rf /var/lib/apt/lists/*  \
    && mkdir -p /project

ENV LC_ALL en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US.UTF-8

RUN conda create -n env python=3.8
RUN echo "source activate env" > ~/.bashrc
ENV PATH /opt/conda/envs/env/bin:$PATH

RUN conda install -n env -c conda-forge earthengine-api==0.1.288
RUN conda install -n env -c conda-forge gdal
RUN conda install -n env requests

COPY gefcore /project/gefcore
COPY main.py /project/main.py

COPY entrypoint.sh /project/entrypoint.sh

RUN chown $USER:$USER /project

WORKDIR /project

ENTRYPOINT ["./entrypoint.sh"]
