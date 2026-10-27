#!/bin/sh
# Atualiza: git pull (se for repositório) e reinstala. Sem git: extraia o patch .zip aqui e rode ./install.sh
set -eu
cd "$(dirname "$0")"
if [ -d .git ] && command -v git >/dev/null 2>&1; then git pull --ff-only; fi
exec ./install.sh "$@"
