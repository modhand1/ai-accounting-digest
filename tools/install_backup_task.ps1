[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDestination,

    [string]$RepositoryPath = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "AI Accounting Digest - verified backup",
    [string]$DailyAt = "20:30",
    [string]$PythonPath,
    [string]$GitPath
)

$ErrorActionPreference = "Stop"

$repository = (Resolve-Path -LiteralPath $RepositoryPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $repository ".git"))) {
    throw "Не найден Git-репозиторий: $repository"
}

if (-not (Test-Path -LiteralPath $BackupDestination)) {
    New-Item -ItemType Directory -Path $BackupDestination | Out-Null
}
$destination = (Resolve-Path -LiteralPath $BackupDestination).Path

if (-not $PythonPath) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python не найден. Передайте полный путь через -PythonPath."
    }
    $PythonPath = $pythonCommand.Source
}

if (-not $GitPath) {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCommand) {
        throw "Git не найден. Передайте полный путь через -GitPath."
    }
    $GitPath = $gitCommand.Source
}

$backupScript = Join-Path $repository "tools\backup_project.py"
if (-not (Test-Path -LiteralPath $backupScript)) {
    throw "Не найден резервный скрипт: $backupScript"
}

Write-Host "Проверяю создание первой резервной копии..."
& $PythonPath $backupScript --repo $repository --destination $destination --git $GitPath
if ($LASTEXITCODE -ne 0) {
    throw "Первая резервная копия не прошла проверку. Задача не создана."
}

$arguments = (
    '"{0}" --repo "{1}" --destination "{2}" --git "{3}"' -f
    $backupScript, $repository, $destination, $GitPath
)
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Проверенная резервная копия публичного origin/main в закрытую папку" `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "Задача создана: $($task.TaskName)"
Write-Host "Расписание: ежедневно в $DailyAt, с запуском после пропущенного времени."
Write-Host "Папка: $destination"
