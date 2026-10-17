# Как залить проект в GitHub

Репозиторий: **https://github.com/b1-o/Jana-Adress** (ветка `main`).

---

# Часть A. Arch Linux + fish (актуальный путь)

## Короткий путь (3 команды, без клонирования и копирования)

Если история коммитов в репозитории не важна — просто отправить папку проекта как есть:

```fish
cd ~/Desktop/jana-v3
git init -q; and git add -A
git -c user.name="b1-o" -c user.email="b1-o@users.noreply.github.com" commit -m "Jana Address: финальная версия по ТЗ"
git remote add origin https://github.com/b1-o/Jana-Adress.git; and git push -u origin main --force
```

Всё старое содержимое ветки `main` заменится этим. `.gitignore` сам уберёт `venv/`, кэши и
`data/official/`. Проверка — просто открыть https://github.com/b1-o/Jana-Adress.

> `--force` перезаписывает ветку. Прежние коммиты остаются в истории, но ветка `main` указывает
> только на новый коммит.

Ниже — длинный путь (с сохранением истории и проверками).


Что попадёт в репозиторий: **68 файлов**, самый большой — `data/gazetteer.sqlite` (23 МБ; лимит GitHub —
100 МБ на файл, так что проходит). Папка `data/official/` (данные организаторов) **не заливается** —
она прописана в `.gitignore`. Папки `venv/`, `.venv/`, кэши `__pycache__/`, `.pytest_cache/` тоже
исключены автоматически.

## Шаг 1. Поставить git и авторизоваться (один раз)

```fish
git --version          # если команда не найдена:  sudo pacman -S git
gh --version           # если команда не найдена:  sudo pacman -S github-cli
```

Дальше — вход в GitHub через `gh` (самый простой способ, пароль не нужен):

```fish
gh auth login
```

Отвечать так:

1. `GitHub.com`
2. `HTTPS`
3. `Login with a web browser` → скопировать код из терминала → Enter → вставить код в браузере
4. На вопрос `Authenticate Git with your GitHub credentials?` → **Yes**

Проверка:

```fish
gh auth status         # должно быть: Logged in to github.com as b1-o
```

## Шаг 2. Поставить имя и почту для коммитов (один раз)

```fish
git config --global user.name "b1-o"
git config --global user.email "b1-o@users.noreply.github.com"
```

## Шаг 3. Скачать репозиторий к себе

```fish
cd ~/Desktop
git clone https://github.com/b1-o/Jana-Adress.git jana-push
cd jana-push
```

## Шаг 4. Заменить старое содержимое новой версией

Сначала убрать из клона все старые файлы (папку `.git` не трогаем — это история репозитория):

```fish
find . -mindepth 1 -maxdepth 1 -not -name .git -exec rm -rf {} +
```

Потом скопировать свежую распакованную версию (**подставь свой путь**, если папка называется иначе):

```fish
cp -a ~/Desktop/jana-v3/. .
```

Убрать мусор, который не должен попасть в репозиторий:

```fish
rm -rf .venv venv .pytest_cache
```

## Шаг 5. Проверить, что заливается именно то, что нужно

```fish
git add -A
git status --short | count          # ожидаем ~68 изменённых файлов
git status --short | grep official  # должно быть пусто (данные организаторов не уходят)
```

Если в списке мелькает `data/official` или `venv` — остановись и напиши, поправим `.gitignore`.

## Шаг 6. Коммит и отправка

```fish
git commit -m "Аудит по ТЗ: 149 тестов, метрика 100%, литера дома, защита batch"
git push origin main
```

Если ветка в репозитории называется не `main`, а `master` — тогда `git push origin HEAD:master`.

## Шаг 7. Проверить результат

```fish
git log --oneline -1                # последний коммит — наш
git ls-files | wc -l                # ≈68
```

Открыть https://github.com/b1-o/Jana-Adress — файлы `app/`, `tests/`, `data/`, `README.md`,
`docker-compose.yml` на месте, дата коммита сегодняшняя.

---

## Вариант A2. «Чистая история» (если нужно перезаписать репозиторий целиком)

Старые коммиты при этом теряются. Делать, только если Вариант A не нужен:

```fish
cd ~/Desktop/jana-v3
git init
git add -A
git commit -m "Jana Address: парсер адресов, справочник КАТО+OSM, API, интерфейс"
git branch -M main
git remote add origin https://github.com/b1-o/Jana-Adress.git
git push -u origin main --force
```

---

## Если что-то пошло не так (Arch / fish)

| Сообщение | Что делать |
|---|---|
| `fatal: could not read Username for 'https://github.com'` | не выполнен вход: `gh auth login`, потом `gh auth setup-git` |
| `remote: Support for password authentication was removed` | пароль не подходит — нужен `gh auth login` или Personal Access Token вместо пароля |
| `! [rejected] main -> main (fetch first)` | `git pull --rebase origin main`, затем снова `git push origin main` |
| `fatal: detected dubious ownership` | `git config --global --add safe.directory ~/Desktop/jana-push` |
| `Permission denied (publickey)` | выбрана SSH-авторизация, а ключа нет — проще перейти на HTTPS: `gh auth login` → HTTPS |
| `error: pathspec 'main' did not match` | ветка называется `master`: `git push origin master` |

---

# Часть B. Windows, командная строка

Ситуация: репозиторий `b1-o/testhackatonrepo` уже создан, локальная папка `D:\testhackatonrepo`
уже связана с ним (`.git` внутри), первый пуш уже сделан. Значит нужно только **обновить файлы и
отправить новый коммит**. Возможны два пути: скрипт-автомат или вручную.

---

## Вариант 1. Полностью заменить содержимое репозитория (удалить всё старое)

Если нужно, чтобы в `b1-o/Jana-Adress` остался только наш проект, а старые файлы (`README.md`,
`1c.god.boss`) исчезли — делается «с чистого листа» с `--force`. Ветка `main` в репозитории
перезаписывается нашей историей, старые файлы из неё удаляются.

### Автоматически — скриптом `push_clean.ps1`

```powershell
cd D:\Ы\jana-address
powershell -ExecutionPolicy Bypass -File .\push_clean.ps1
# другой репозиторий:  -RepoUrl https://github.com/b1-o/testhackatonrepo.git
# без вопросов:        -Yes
```

Скрипт проверит, что в папке лежит проект (Dockerfile, `app/parser.py`, справочник), сделает коммит
и выполнит `push --force`, а затем покажет, сколько файлов оказалось в репозитории.

### Вручную — те же 6 команд

```powershell
cd D:\Ы\jana-address
git init
git add .
git commit -m "Jana Address: парсер адресов, справочник КАТО+OSM, районы Алматы, API, интерфейс"
git remote add origin https://github.com/b1-o/Jana-Adress.git
git branch -M main
git push -u origin main --force
```

Проверка результата:

```powershell
git remote -v                     # origin = нужный репозиторий
(git ls-files).Count              # ≈41 файл
git ls-files data/official        # должно быть пусто
```

> ⚠️ `--force` перезаписывает ветку. Прежние коммиты становятся недостижимыми (по прямым SHA
> на GitHub они какое-то время ещё открываются). Нужна **абсолютно** чистая история — тогда проще
> удалить репозиторий и создать заново: *Settings → General → внизу Delete this repository*,
> затем *New repository* с тем же именем, и уже туда сделать обычный `push`.
> Приватный `testhackatonrepo` при этом никак не затрагивается.

---

## Вариант 2. Обновить файлы поверх существующего репозитория (`deploy.ps1`)

Что он делает сам: распаковывает свежий архив → копирует файлы поверх папки репозитория
(папку `.git` и `data/official` не трогает) → поднимает контейнер и проверяет, что `/api/health`
отвечает (с замером времени, лимит ТЗ — 3 минуты) → спрашивает подтверждение и делает
`git add / commit / push`.

```powershell
# 1. скачать свежий jana-address-src.zip из воркспейса в Загрузки
# 2. один раз снять «блокировку скачанного файла» (Windows помечает файлы из интернета)
Unblock-File "$HOME\Downloads\jana-address-src.zip"

# 3. запустить развёртывание
powershell -ExecutionPolicy Bypass -File "$HOME\Downloads\jana-address\deploy.ps1" -RepoPath D:\testhackatonrepo
```

Полезные ключи:

| Ключ | Зачем |
|---|---|
| `-RepoPath D:\testhackatonrepo` | папка локального репозитория |
| `-Source <путь к zip>` | если архив лежит не в Загрузках |
| `-SkipDocker` | не поднимать контейнер (обновить и запушить без проверки) |
| `-NoPush` | только обновить файлы, git не трогать |
| `-Yes` | не спрашивать подтверждение перед пушем |

---

## Вариант 3. Вручную, без скриптов (5 команд)

```powershell
# 1. распаковать свежий архив
Expand-Archive -Path "$HOME\Downloads\jana-address-src.zip" -DestinationPath "$HOME\Downloads\jana-new" -Force

# 2. скопировать файлы поверх репозитория (папку .git не трогаем)
robocopy "$HOME\Downloads\jana-new\jana-address" "D:\testhackatonrepo" /E /XD ".git" ".venv" "__pycache__"

# 3. проверить, что видит git
cd D:\testhackatonrepo
git status --short

# 4. закоммитить
git add .
git commit -m "UI: пошаговый интерфейс; справочник: районы Алматы по полигонам"

# 5. запушить
git push
```

`git push` спросит логин/токен только если не сохранён Git Credential Manager — обычно он уже
авторизован после первого пуша.

### Если push отклонён («rejected / fetch first»)
Значит в удалённом репозитории появились новые коммиты (например, кто-то из команды залил свои):

```powershell
git pull --rebase origin main       # подтянуть и переприменить свой коммит
git push
```

### Если хочется перезаписать удалённое содержимое целиком
```powershell
git push --force
```
Так делать стоит только если уверены, что чужих коммитов там нет.

---

## Вариант 4. Склонировать репозиторий и скопировать проект внутрь

Репозиторий `b1-o/Jana-Adress` **не пустой**: там старый `README.md` и два файла `1c.god.boss`.
Поэтому «поверх пушить» неудобно — проще склонировать его и скопировать проект внутрь:
история сохранится, конфликтов «unrelated histories» не будет.

```powershell
# 1. клонировать репозиторий рядом (можно любую папку без кириллицы в пути)
git clone https://github.com/b1-o/Jana-Adress.git D:\jana-address-gh

# 2. скопировать проект из распакованного архива в клон (.git не трогаем)
robocopy "D:\Ы\jana-address" "D:\jana-address-gh" /E /XD ".git" ".venv" "__pycache__"

# 3. запушить
cd D:\jana-address-gh
git status --short          # посмотреть, что попадает в коммит
git add .
git commit -m "Jana Address: парсер адресов, справочник КАТО+OSM, районы Алматы, REST API, интерфейс"
git push
```

Проверка, что пушим именно туда, куда надо:

```powershell
git remote -v              # должно быть: origin  https://github.com/b1-o/Jana-Adress.git
```

Дальше по желанию — убрать лишние файлы, оставшиеся от прежней версии репозитория:

```powershell
git rm --cached 1c.god.boss 1c.god.boss. 2>$null
git commit -m "Удалены служебные файлы прежней версии"
git push
```

Если папка с кириллицей в пути мешает работе команд (бывает в старом `cmd`),
переименуйте её в латиницу: `Rename-Item D:\Ы D:\jana`.

---

## Проверка после пуша

```powershell
(git ls-files).Count                  # ≈38 файлов
git ls-files data/official            # должно быть пусто — данные организаторов не выкладываем
git ls-files "data/districts/*"       # должны быть полигоны районов (Алматы)
docker compose up --build             # и открыть http://localhost:8000
```

На странице GitHub в списке файлов появятся `deploy.ps1`, `data/districts/`, обновлённые
`app/static/index.html` и `README.md`.

---

## Что изменилось в этой версии

**Коротко: разбор теперь работает на русском, казахском и английском, а справочник вырос
с 5 городов до 28.** Если у вас уже лежит свежий `main` с GitHub, достаточно заменить
9 файлов — список в `ЧТО_ОБНОВИТЬ_СЕЙЧАС.md`. Если начинали с нуля — просто кладите архив целиком.

| Файл | Что нового |
|---|---|
| `app/static/index.html` | интерфейс переделан: три подписанных шага, кнопка «Показать пример», понятные статусы после разбора, переключатели «Все / Неуверенные / Исправленные», зелёная подсветка полей из справочника, блок «Как это работает», сверка с эталоном и выгрузка JSON/CSV |
| `data/districts/Алматы.json` | полигоны районов Алматы (8 районов) — на них теперь строится восстановление `district` |
| `scripts/fetch_districts.py` | сбор границ районов; в текущем OSM геометрия районов городов республиканского значения удалена, поэтому используется GeoJSON-экстракт OSM (лежит в `data/source/`) |
| `scripts/build_gazetteer.py` | улицы и микрорайоны раскладываются по районам point-in-polygon с «голосованием» по сегментам улицы; в справочнике видны источники |
| `scripts/selfcheck.py` | самопроверка: справочник, 15 контрольных адресов, скорость, полнота полей |
| `tests/test_parser.py` | добавлены тесты на восстановление района (включая официальный пример `rec_00417` → «Ауэзовский») и на приоритет строки над справочником |
| `deploy.ps1` | этот скрипт развёртывания |
| `README.md` | разделы «Проверка работоспособности», «Как проверялось качество», источник границ районов |
| `push_clean.ps1` | полная замена содержимого репозитория (git init + push --force) с проверками |
| `app/lang.py` | **новый**: три языка — транслит латиницы, типы улиц EN/KZ, админ-слова |
| `app/parser.py` | типы и маркеры на EN/KZ, литера дома, ложное «тоқсан» в «Желтоқсан», жилмассив раньше улицы |
| `app/preprocessor.py` | склейки «Алматыул.Абая12», точка без пробела, латиница+цифра |
| `app/textnorm.py` | ключи поиска с транслитом |
| `app/gazetteer.py` | транслит, изоляция города, префиксный поиск только для одного слова |
| `app/confidence.py` | уверенность стала доказательной: подтверждённая справочником улица — выше |
| `app/fuzzy.py` | исправлен кэш: результат по улицам больше не подставляется жилмассивам |
| `data/gazetteer.sqlite` | 33 095 улиц по 28 городам (было 12 344 по 5) |
| `scripts/expand_streets.py` | **новый**: дозагрузка улиц из OSM |
| `tests/test_multilang.py`, `tests/test_formats.py` | **новые**: 25 регрессионных тестов |
| `README.md` | разделы 4.1 «Три языка» и 4.2 «Справочник улиц» |

---

## Если что-то пошло не так

| Симптом | Лечение |
|---|---|
| `deploy.ps1: невозможно загрузить файл, так как выполнение сценариев отключено` | запускать с `-ExecutionPolicy Bypass`, как в команде выше |
| `Не найден архив` | укажите путь явно: `-Source "D:\путь\jana-address-src.zip"` |
| Docker не отвечает за 3 минуты | `docker compose logs --tail 50` — обычно не запущен Docker Desktop |
| `git push` просит пароль | нужен Personal Access Token со scope `repo` (Settings → Developer settings → Tokens (classic)) |
| Хочется начать «с чистого листа» | `Remove-Item D:\testhackatonrepo -Recurse -Force` и клонировать заново: `git clone <URL>` |
