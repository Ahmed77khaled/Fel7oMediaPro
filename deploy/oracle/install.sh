#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/fel7o-media-pro
SERVICE_NAME=fel7o-media-pro.service

if [[ $EUID -ne 0 ]]; then
  echo "Run this script with sudo."
  exit 1
fi

if [[ ! -f "$APP_DIR/main.py" ]]; then
  echo "Project files must be uploaded to $APP_DIR first."
  exit 1
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "Create $APP_DIR/.env from .env.example and add the bot token first."
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg

id -u fel7o >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin fel7o
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

install -m 644 "$APP_DIR/deploy/oracle/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
chown -R fel7o:fel7o "$APP_DIR"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME"
