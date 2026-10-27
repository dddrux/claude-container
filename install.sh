#!/bin/sh
# Instalador Linux (sem AppImage). Por usuário, sem sudo. Rodar de novo = atualizar.
#   ./install.sh            instala/atualiza (copia o app para ~/.local/share/claude-containers-app)
#   ./install.sh --link     usa esta pasta direto (patches extraídos aqui valem na hora)
#   ./install.sh --uninstall [--purge]   remove (--purge apaga também perfis/logins/config)
# Requer python3 + python3-venv. Se o app não abrir: libxcb-cursor0 libnss3 libxkbcommon-x11-0 libegl1
set -eu

NAME=claude-containers
SRC="$(cd "$(dirname "$0")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/$NAME-app"
PD="$DATA_HOME/$NAME"            # dados do usuário (perfis, pausas) — nunca é apagado ao atualizar
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor"
SIZES="16 24 32 48 64 128 256 512"

die() { echo "erro: $*" >&2; exit 1; }

refresh_caches() {
  command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -f -t "$ICON_DIR" >/dev/null 2>&1 || true
}

uninstall() {
  rm -f "$BIN_DIR/$NAME" "$APPS_DIR/$NAME.desktop"
  for s in $SIZES; do rm -f "$ICON_DIR/${s}x${s}/apps/$NAME.png"; done
  if [ -L "$APP_DIR" ]; then rm -f "$APP_DIR"; else rm -rf "$APP_DIR"; fi
  rm -f "$PD/mode" "$PD/version"
  refresh_caches
  echo "Removido."
  if [ "${PURGE:-0}" = 1 ]; then
    printf "Apagar TODOS os perfis/logins em %s e ~/.config/%s? [s/N] " "$PD" "$NAME"
    read -r a
    case "$a" in s|S|y|Y) rm -rf "$PD" "$HOME/.config/$NAME"; echo "Dados apagados." ;; esac
  else
    echo "Perfis e logins mantidos em $PD (use --purge para apagar)."
  fi
}

MODE=""; DO_UNINSTALL=0; PURGE=0
for a in "$@"; do
  case "$a" in
    --link) MODE=link ;;
    --copy) MODE=copy ;;
    --uninstall) DO_UNINSTALL=1 ;;
    --purge) PURGE=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) die "opção desconhecida: $a" ;;
  esac
done
[ "$DO_UNINSTALL" = 1 ] && { uninstall; exit 0; }

command -v python3 >/dev/null 2>&1 || die "python3 não encontrado"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || die "precisa de Python 3.9+"
[ -f "$SRC/main.py" ] && [ -f "$SRC/requirements.txt" ] || die "rode o install.sh na pasta do projeto"
mkdir -p "$PD" "$BIN_DIR" "$APPS_DIR"
[ -z "$MODE" ] && MODE="$(cat "$PD/mode" 2>/dev/null || echo copy)"

OLD="$(cat "$PD/version" 2>/dev/null || true)"
NEW="$(cat "$SRC/VERSION" 2>/dev/null || echo dev)"

# 1) código
if [ "$MODE" = link ]; then
  if [ ! -L "$APP_DIR" ] && [ -d "$APP_DIR" ] && [ "$APP_DIR" != "$SRC" ]; then rm -rf "$APP_DIR"; fi
  [ "$APP_DIR" = "$SRC" ] || ln -sfn "$SRC" "$APP_DIR"
else
  [ -L "$APP_DIR" ] && rm -f "$APP_DIR"
  mkdir -p "$APP_DIR/assets"
  if [ "$APP_DIR" != "$SRC" ]; then
    cp -f "$SRC/main.py" "$SRC/requirements.txt" "$APP_DIR/"
    [ -f "$SRC/VERSION" ] && cp -f "$SRC/VERSION" "$APP_DIR/"
    cp -f "$SRC/assets/icon.png" "$APP_DIR/assets/"
  fi
fi

# 2) dependências (só reinstala se requirements.txt mudou)
cd "$APP_DIR"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || die "falhou criar venv (Debian/Ubuntu: sudo apt install python3-venv)"
fi
H="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ "$(cat .venv/.req-hash 2>/dev/null || true)" != "$H" ]; then
  echo "Instalando dependências..."
  .venv/bin/pip install -q -r requirements.txt
  echo "$H" > .venv/.req-hash
fi

# 3) lançador
cat > "$BIN_DIR/$NAME" <<LAUNCH
#!/bin/sh
export CC_INSTALLED=1
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/main.py" "\$@"
LAUNCH
chmod +x "$BIN_DIR/$NAME"

# 4) ícones (hicolor) + .desktop (GNOME)
for s in $SIZES; do
  [ -f "$SRC/assets/icons/$s.png" ] || continue
  mkdir -p "$ICON_DIR/${s}x${s}/apps"
  cp -f "$SRC/assets/icons/$s.png" "$ICON_DIR/${s}x${s}/apps/$NAME.png"
done
cat > "$APPS_DIR/$NAME.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Claude Containers
Comment=Claude com um perfil isolado por conta
Exec=$BIN_DIR/$NAME
Icon=$NAME
Terminal=false
Categories=Network;Chat;
StartupWMClass=$NAME
DESK
chmod 644 "$APPS_DIR/$NAME.desktop"
refresh_caches

# 5) migra pausas.json antigo (raiz do projeto) uma única vez
if [ -f "$SRC/pausas.json" ] && [ ! -f "$PD/pausas.json" ]; then cp "$SRC/pausas.json" "$PD/pausas.json"; fi

echo "$MODE" > "$PD/mode"
echo "$NEW" > "$PD/version"
if [ -n "$OLD" ] && [ "$OLD" != "$NEW" ]; then echo "Atualizado: v$OLD -> v$NEW ($MODE). Reabra o app."
elif [ -n "$OLD" ]; then echo "Reinstalado v$NEW ($MODE). Reabra o app."
else echo "Instalado v$NEW ($MODE). Abra 'Claude Containers' no menu de aplicativos."; fi
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "Dica: adicione $BIN_DIR ao PATH para usar o comando '$NAME'." ;; esac
