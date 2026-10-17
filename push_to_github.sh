#!/usr/bin/env bash
# Отправка проекта на GitHub одной командой:  bash push_to_github.sh
# Скрипт должен лежать ВНУТРИ папки проекта (рядом с Dockerfile).
# Репозиторий по умолчанию: https://github.com/b1-o/Jana-Adress.git
# Другой репозиторий:  REPO_URL=https://github.com/user/repo.git bash push_to_github.sh

set -e

REPO_URL="${REPO_URL:-https://github.com/b1-o/Jana-Adress.git}"
BRANCH="${BRANCH:-main}"
COMMIT_MSG="${COMMIT_MSG:-Jana Address: финальная версия по ТЗ}"

say() { printf '\n\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mОШИБКА: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------- 1. Проверяем, что мы в правильной папке ----------
say "1/6  Проверяю папку…"

[ -f Dockerfile ] || die "в этой папке нет Dockerfile — значит это не папка проекта.
Перейди в папку, где лежат Dockerfile, app/, data/, README.md, и запусти скрипт оттуда:
    cd ~/Desktop/jana-v3
    bash push_to_github.sh"

[ -f app/parser.py ] || die "нет app/parser.py — это не папка проекта."

if [ -d jana-v3 ] || [ -d jana-address-v3 ]; then
  die "внутри лежит ещё одна папка с проектом — файлы распаковались на уровень глубже.
Нужно, чтобы Dockerfile, app/, data/ лежали СРАЗУ в этой папке, а не внутри вложенной."
fi

echo "     папка: $(pwd)"
echo "     файлов в проекте: $(find . -type f -not -path './.git/*' | wc -l)"

# ---------- 2. Проверяем git и вход в GitHub ----------
say "2/6  Проверяю git…"
command -v git >/dev/null 2>&1 || die "git не установлен.  Установи: sudo pacman -S git"
git --version

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "     вход в GitHub: OK ($(gh api user --jq .login 2>/dev/null))"
else
  warn "     вход в GitHub не найден. Если git попросит логин — отмени (Ctrl+C) и выполни:
       sudo pacman -S github-cli
       gh auth login        # GitHub.com → HTTPS → Login with a web browser → Yes"
fi

# ---------- 3. Инициализация репозитория ----------
say "3/6  Готовлю репозиторий…"
if [ -d .git ]; then
  echo "     .git уже есть — используем его"
else
  git init -q
  git branch -M "$BRANCH" 2>/dev/null || true
  echo "     создан новый репозиторий"
fi

# имя автора коммита, если в системе не настроено
if [ -z "$(git config user.email || true)" ]; then
  GIT_ID=(-c user.name="b1-o" -c user.email="b1-o@users.noreply.github.com")
  echo "     автор коммита: b1-o (по умолчанию)"
else
  GIT_ID=()
  echo "     автор коммита: $(git config user.name) <$(git config user.email)>"
fi

# ---------- 4. Добавляем файлы ----------
say "4/6  Добавляю файлы (служебные исключаются через .gitignore)…"
git add -A

if git ls-files | grep -q '^data/official'; then
  die "в коммит попали данные организаторов (data/official) — так нельзя.
Проверь .gitignore, строка 'data/official/' должна быть на месте."
fi

COUNT=$(git ls-files | wc -l)
SIZE=$(du -sh .git 2>/dev/null | cut -f1)
echo "     файлов к отправке: $COUNT"
[ "$COUNT" -gt 0 ] || die "нечего отправлять — файлы не добавились."

BIGGEST=$(git ls-files -z | xargs -0 du -h 2>/dev/null | sort -rh | head -1 | cut -f2)
echo "     самый крупный файл: $BIGGEST"

# ---------- 5. Коммит ----------
say "5/6  Делаю коммит…"
if git diff --cached --quiet; then
  echo "     изменений нет — коммит не нужен"
else
  git "${GIT_ID[@]}" commit -q -m "$COMMIT_MSG"
  echo "     готово: $(git log --oneline -1)"
fi

# ---------- 6. Отправка ----------
say "6/6  Отправляю на GitHub…"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REPO_URL"
else
  git remote add origin "$REPO_URL"
fi
echo "     адрес: $REPO_URL"
echo "     ветка: $BRANCH"
echo

if git push -u origin "$BRANCH" --force; then
  say "ГОТОВО. Проверь страницу:"
  echo "     ${REPO_URL%.git}"
else
  die "push не прошёл. Частые причины:
  • не выполнен вход:      gh auth login   (GitHub.com → HTTPS → браузер → Yes)
  • ветка называется master:  BRANCH=master bash push_to_github.sh
  • нет прав на репозиторий:  проверь, что ты владелец b1-o/Jana-Adress"
fi
