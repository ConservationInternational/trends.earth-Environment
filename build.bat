@echo off
for /f %%i in ('git rev-parse --short HEAD') do set GIT_SHA=%%i
docker build --build-arg GIT_SHA=%GIT_SHA% -t conservationinternational/trends.earth-environment:2.2.2 .
docker push conservationinternational/trends.earth-environment:2.2.2