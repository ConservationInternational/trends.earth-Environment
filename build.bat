@echo off
for /f %%i in ('git describe --always --dirty') do set GIT_SHA=%%i
echo Building with GIT_SHA=%GIT_SHA%
docker build --no-cache --build-arg GIT_SHA=%GIT_SHA% -t conservationinternational/trends.earth-environment:2.2.2 .
docker push conservationinternational/trends.earth-environment:2.2.2