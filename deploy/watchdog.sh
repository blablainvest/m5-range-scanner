#!/bin/sh
set -eu

cd /opt/m5-scanner

if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

if ! /usr/bin/docker info >/dev/null 2>&1; then
    /usr/bin/systemctl restart docker
    sleep 10
fi

/usr/bin/docker compose up -d --remove-orphans >/dev/null

for service in postgres backend worker frontend; do
    container_id=$(/usr/bin/docker compose ps -q "$service")
    if [ -z "$container_id" ] || [ "$(/usr/bin/docker inspect -f '{{.State.Running}}' "$container_id")" != "true" ]; then
        /usr/bin/docker compose up -d "$service" >/dev/null
    fi
done

last_completed=$(
    /usr/bin/docker compose exec -T postgres psql \
        -U "${POSTGRES_USER:-m5_scanner}" \
        -d "${POSTGRES_DB:-m5_scanner}" \
        -Atc "select coalesce(extract(epoch from max(scheduled_at))::bigint, 0) from scan_runs where status = 'COMPLETED';"
)
now_epoch=$(/usr/bin/date +%s)
if [ "$last_completed" -eq 0 ] || [ $((now_epoch - last_completed)) -gt "${SCAN_STALE_AFTER_SECONDS:-2700}" ]; then
    /usr/bin/docker compose restart worker >/dev/null
fi

if ! /usr/bin/curl --fail --silent --max-time 15 http://127.0.0.1/api/health >/dev/null; then
    /usr/bin/docker compose restart backend frontend >/dev/null
    sleep 15
    /usr/bin/curl --fail --silent --max-time 15 http://127.0.0.1/api/health >/dev/null
fi

disk_usage=$(/bin/df -P /var/lib/docker | /usr/bin/awk 'NR==2 {gsub("%", "", $5); print $5}')
if [ "${disk_usage:-0}" -ge 70 ]; then
    /usr/bin/logger -p user.warning -t m5-scanner "Docker disk usage is ${disk_usage}% (threshold 70%)"
fi
