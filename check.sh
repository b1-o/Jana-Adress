#!/usr/bin/env bash
# Проверка версии проекта и того, что отдаёт запущенный сервер.
cd "$(dirname "$0")"
exec python check_version.py "$@"
