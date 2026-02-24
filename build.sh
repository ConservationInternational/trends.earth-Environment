#!/bin/bash
set -e
GIT_SHA=$(git rev-parse --short HEAD)
docker build --build-arg GIT_SHA="$GIT_SHA" -t conservationinternational/trends.earth-environment:2.2.2 .
docker push conservationinternational/trends.earth-environment:2.2.2