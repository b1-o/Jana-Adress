<#
    push_clean.ps1 — полностью заменить содержимое репозитория на наш проект.

    Что делает:
      1) проверяет, что мы в папке с проектом (есть Dockerfile и app/parser.py);
      2) git init + коммит всего проекта (папки .git, .venv, __pycache__ исключены);
      3) привязывает remote и делает push --force: старые файлы в репозитории исчезают.

    Запуск (PowerShell из папки проекта):
        powershell -ExecutionPolicy Bypass -File .\push_clean.ps1
        # другой репозиторий или папка:
        powershell -ExecutionPolicy Bypass -File .\push_clean.ps1 -RepoUrl <URL> -Path D:\Ы\jana-address

    ВНИМАНИЕ: --force перезаписывает историю удалённого репозитория. Все файлы, которые были
    там раньше, из ветки удаляются. Убедитесь, что в репозитории нет ничего нужного
    (у нас в b1-o/Jana-Adress были только заглушка README.md и файлы 1c.god.boss).
#>
param(
    [string]$RepoUrl = "https://github.com/b1-o/Jana-Adress.git",
    [string]$Path    = ".",
    [string]$Message = "Jana Address: parser, gazetteer (KATO+OSM), REST API, UI",
    [switch]$Yes      # не спрашивать подтверждение
)

$ErrorActionPreference = "Stop"
function Say($t, $c = "Cyan") { Write-Host $t -ForegroundColor $c }

Set-Location -Path $Path
$here = (Get-Location).Path
Say "Папка проекта: $here"

# --- проверки ---------------------------------------------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Say "git не найден. Установите: winget install --id Git.Git -e --source winget" Red
    exit 1
}
foreach ($need in @("Dockerfile", "app\parser.py", "data\gazetteer.sqlite")) {
    if (-not (Test-Path (Join-Path $here $need))) {
        Say "Не вижу '$need' — похоже, это не папка проекта Jana Address." Red
        Say "Укажите её явно: -Path D:\путь\к\jana-address" Red
        exit 1
    }
}
Say "Проверки пройдены: Dockerfile, app\parser.py, справочник на месте."

# --- предупреждение ---------------------------------------------------------
Say "`nВНИМАНИЕ: будет выполнен push --force в $RepoUrl" Yellow
Say "Всё, что лежит в репозитории сейчас, из ветки main исчезнет и заменится на этот проект." Yellow
if (-not $Yes) {
    $answer = Read-Host "Продолжить? (введите y)"
    if ($answer -ne "y") { Say "Отменено." ; exit 0 }
}

# --- локальный репозиторий --------------------------------------------------
if (-not (Test-Path ".git")) { git init | Out-Null; Say "Создан локальный репозиторий" }
git checkout -B main | Out-Null

# если папка уже была репозиторием с чужими файлами в индексе — начинаем с чистого индекса
git rm -r --cached . 2>$null | Out-Null

git add .
$count = (git diff --cached --name-only | Measure-Object).Count
Say "Файлов в коммите: $count"

git -c user.name="b1-o" -c user.email="b1-o@users.noreply.github.com" commit -m $Message | Out-Null

# --- восстановим .gitignore-папки, которые не должны попасть в коммит -------
$forbidden = git ls-files | Where-Object { $_ -like "data/official/*" -or $_ -like "*.pyc" }
if ($forbidden) {
    Say "В коммит попали служебные файлы — убираю: $($forbidden -join ', ')" Yellow
    $forbidden | ForEach-Object { git rm --cached $_ | Out-Null }
    git -c user.name="b1-o" -c user.email="b1-o@users.noreply.github.com" commit -m "Не коммитим служебные файлы" | Out-Null
}

# --- remote и push ---------------------------------------------------------
$remotes = git remote
if ($remotes -contains "origin") { git remote set-url origin $RepoUrl } else { git remote add origin $RepoUrl }
Say "origin -> $RepoUrl"

git push -u origin main --force
if ($LASTEXITCODE -ne 0) {
    Say "`nPush не прошёл. Частые причины:" Yellow
    Say "  • нет прав/не тот аккаунт — проверьте: git remote -v и логин в Git Credential Manager"
    Say "  • нужен Personal Access Token со scope repo (вместо пароля)"
    exit 1
}

Say "`nГОТОВО ✅" Green
Say "Файлов в репозитории: $((git ls-files | Measure-Object).Count)"
Say "Проверка, что данные организаторов не улетели: data/official -> $((git ls-files 'data/official' | Measure-Object).Count) файлов (ожидаем 0)"
Say "Откройте $RepoUrl — там должен быть наш README и папки app, data, scripts, tests."
