<#
    deploy.ps1 — обновить проект в локальной папке репозитория, проверить Docker'ом и запушить.

    Что делает:
      1) распаковывает свежий jana-address-src.zip во временную папку;
      2) копирует файлы поверх твоей локальной папки репозитория (папку .git и data/official не трогает);
      3) запускает docker compose up --build и ждёт, пока контейнер ответит на /api/health
         (не дольше 3 минут — это требование кейса), измеряет время запуска;
      4) спрашивает подтверждение и делает git add / commit / push.

    Запуск (PowerShell, из любой папки):
        powershell -ExecutionPolicy Bypass -File "$HOME\Downloads\jana-address\deploy.ps1"
        # или с параметрами:
        powershell -ExecutionPolicy Bypass -File deploy.ps1 -RepoPath D:\testhackatonrepo -SkipDocker
#>
param(
    [string]$RepoPath = "D:\testhackatonrepo",
    [string]$Source   = "$HOME\Downloads\jana-address-src.zip",
    [string]$Message  = "UI: пошаговый интерфейс; справочник: районы Алматы по полигонам",
    [switch]$SkipDocker,      # не запускать проверку Docker
    [switch]$NoPush,          # только обновить файлы, без git
    [switch]$Yes              # не спрашивать подтверждение перед push
)

$ErrorActionPreference = "Stop"
function Say($text, $color = "Cyan") { Write-Host $text -ForegroundColor $color }

# ----------------------------------------------------------------- 0. проверки
if (-not (Test-Path $Source)) {
    Say "Не найден архив: $Source" Red
    Say "Скачайте jana-address-src.zip из воркспейса и положите рядом — или укажите путь: -Source <путь>" Red
    exit 1
}
if (-not (Test-Path $RepoPath)) {
    Say "Не найдена папка репозитория: $RepoPath" Red
    Say "Укажите её явно: -RepoPath D:\путь\к\репозиторию" Red
    exit 1
}
Say "Архив:   $Source"
Say "Репозиторий: $RepoPath"

# ----------------------------------------------------------------- 1. распаковка
$tmp = Join-Path $env:TEMP ("jana-" + (Get-Random))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Expand-Archive -Path $Source -DestinationPath $tmp -Force
$srcDir = Join-Path $tmp "jana-address"
if (-not (Test-Path $srcDir)) { Say "В архиве нет папки jana-address" Red; exit 1 }
Say "Распаковано во временную папку: $tmp"

# ----------------------------------------------------------------- 2. копирование
Say "`n[1/4] Копирую файлы в репозиторий…"
# копируем всё, кроме служебных папок; /XD принимает имена папок без путей
robocopy $srcDir $RepoPath /E /XD ".git" ".venv" "__pycache__" "official" "reports" /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Say "robocopy вернул код $LASTEXITCODE — проверьте права на папку" Red; exit 1 }
# убираем служебные файлы, которые не должны попасть в репозиторий
foreach ($junk in @("push_to_github.ps1", "push_to_github.sh", "PUSH_TO_GITHUB.md")) {
    $p = Join-Path $RepoPath $junk
    if (Test-Path $p) { Remove-Item $p -Force; Say "  убрал служебный файл: $junk" Yellow }
}
Say "  готово. Файлы в репозитории: $((Get-ChildItem $RepoPath -Recurse -File | Where-Object { $_.FullName -notlike "*\.git\*" }).Count)"

if ($NoPush) { Say "`nФлаг -NoPush: файлы обновлены, git не трогаю." Green; exit 0 }

# ----------------------------------------------------------------- 3. Docker-проверка
if (-not $SkipDocker) {
    Say "`n[2/4] Проверяю запуск через Docker (лимит ТЗ — 3 минуты)…"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Say "  docker не найден в PATH — пропускаю проверку (запустите Docker Desktop и повторите)" Yellow
    } else {
        Push-Location $RepoPath
        $t0 = Get-Date
        docker compose up -d --build 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
        $ok = $false
        for ($i = 0; $i -lt 36; $i++) {
            Start-Sleep -Seconds 5
            try {
                $r = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 4 -ErrorAction Stop
                if ($r.status -eq "ok") { $ok = $true; break }
            } catch { }
        }
        $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
        if ($ok) {
            Say "  контейнер поднялся за $sec c и отвечает: status=ok" Green
            Say "  справочник: $($r.gazetteer.summary)"
            docker compose exec -T jana-address python scripts/selfcheck.py 2>&1 |
                ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            Say "  интерфейс: http://localhost:8000" Green
        } else {
            Say "  за 3 минуты контейнер не ответил — посмотрите вывод выше (docker compose logs)" Red
        }
        Pop-Location
    }
}

# ----------------------------------------------------------------- 4. git push
Say "`n[3/4] Готовлю коммит…"
Push-Location $RepoPath
if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
    Say "  папка не под git — создаю репозиторий" Yellow
    git init | Out-Null
    git checkout -B main | Out-Null
    if (-not (git remote)) { Say "  добавьте remote вручную: git remote add origin <URL>" Yellow }
}
git add .
$changed = (git diff --cached --name-only | Measure-Object).Count
if ($changed -eq 0) {
    Say "  изменений нет — пушить нечего" Yellow
    Pop-Location; exit 0
}
Say "  файлов в коммите: $changed"
git commit -m $Message | Out-Null

if (-not $Yes) {
    $answer = Read-Host "`n[4/4] Отправить коммит на GitHub? (y/n)"
    if ($answer -ne "y") { Say "Отменено. Коммит остался локально — можно запушить позже: git push" Yellow; Pop-Location; exit 0 }
}
git push
Pop-Location

Say "`nГОТОВО ✅  Проверьте страницу репозитория на GitHub." Green
Say "Если push отклонён — в удалённом репозитории есть новые коммиты: git pull --rebase и снова git push" Yellow
