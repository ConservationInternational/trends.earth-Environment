FROM ghcr.io/osgeo/gdal:ubuntu-small-3.11.3
LABEL maintainer="Alex Zvoleff <azvoleff@conservation.org>"

ENV USER=script
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
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# --- pip install layer (cached until requirements.txt changes) ---
COPY requirements.txt /project/requirements-environment.txt
RUN pip install --no-cache-dir -r /project/requirements-environment.txt

# Bake the git commit SHA into the image so every execution can be
# traced back to the exact source that built it.  Placing the ARG
# before the source COPY commands means a new commit (different SHA)
# invalidates the Docker cache for all source layers below.
ARG GIT_SHA=unknown

# --- Source layers: least-frequently-changed files first ---
COPY --chown=script:script entrypoint.sh /project/entrypoint.sh
COPY --chown=script:script main.py /project/main.py
COPY --chown=script:script gefcore /project/gefcore

ENV GIT_SHA=${GIT_SHA}

# Ensure the script user owns /project so entrypoint.sh can write
# temporary files (e.g. service_account.json) at runtime.
RUN chown $USER:$USER /project

WORKDIR /project

ENTRYPOINT ["./entrypoint.sh"]
