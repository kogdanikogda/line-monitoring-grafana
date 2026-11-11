#!/bin/sh
# Demo Grafana next to the existing VPN. Touches only containers "neuroprom-grafana" and "neuroprom-caddy".
set -e
cd /opt/neuroprom-grafana
[ -f admin.pass ] || (head -c 18 /dev/urandom | base64 | tr -d '/+=' > admin.pass; chmod 600 admin.pass)
docker network inspect neuroprom >/dev/null 2>&1 || docker network create neuroprom
docker build -q -t neuroprom-grafana:12.4.0 .
docker rm -f neuroprom-grafana neuroprom-caddy >/dev/null 2>&1 || true
docker run -d --name neuroprom-grafana --network neuroprom --restart unless-stopped --memory 400m \
  -v neuroprom-grafana-data:/var/lib/grafana/data \
  -e GF_PATHS_DATA=/var/lib/grafana/data \
  -e GF_SERVER_ROOT_URL=https://77-238-227-42.sslip.io:8443/ \
  -e GF_SECURITY_ADMIN_PASSWORD="$(cat admin.pass)" \
  -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \
  -e GF_USERS_DEFAULT_LANGUAGE=ru-RU -e GF_USERS_DEFAULT_THEME=light \
  -e GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/line.json \
  -e GF_ANALYTICS_REPORTING_ENABLED=false -e GF_ANALYTICS_CHECK_FOR_UPDATES=false -e GF_NEWS_NEWS_FEED_ENABLED=false \
  -e GF_SECURITY_COOKIE_SECURE=true \
  neuroprom-grafana:12.4.0
docker run -d --name neuroprom-caddy --network neuroprom --restart unless-stopped --memory 64m \
  -p 80:80 -p 8443:8443 -v /opt/neuroprom-grafana/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v neuroprom-caddy-data:/data caddy:2.10
docker ps --format '{{.Names}} {{.Status}}'
