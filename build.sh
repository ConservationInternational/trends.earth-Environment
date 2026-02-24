#!/bin/bash
set -e
GIT_SHA=$(git describe --always --dirty)
echo "Building with GIT_SHA=$GIT_SHA"
docker build --no-cache --build-arg GIT_SHA="$GIT_SHA" -t conservationinternational/trends.earth-environment:2.2.2 .
docker push conservationinternational/trends.earth-environment:2.2.2