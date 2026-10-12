# One-time setup: registers the "revenue-console-deploy" scheduled task that runs
# scripts\deploy.cmd with "Run whether user is logged on or not", which gives
# Docker Desktop's credential helper the DPAPI access SSH pubkey logins lack.
# Run locally at the machine (not over SSH); prompts for the Windows password in
# a dialog so it never lands in shell history. Registering a stored-password task
# needs admin rights, and "The Anvaya Bali" is a standard account, so this runs
# elevated (as an admin account) but registers the task for -UserName and grants
# that account read/run access - otherwise it can't trigger the task over SSH -
# plus "Log on as a batch job", without which the task can't log on at all.
# -GrantOnly re-applies just those grants to an existing task (no password).
param(
    [string]$UserName = 'The Anvaya Bali',
    [switch]$GrantOnly
)
$ErrorActionPreference = 'Stop'
$taskName = 'revenue-console-deploy'

if (-not $GrantOnly) {
    $deployScript = Join-Path $PSScriptRoot 'deploy.cmd'
    $cred = Get-Credential -UserName "$env:COMPUTERNAME\$UserName" -Message "Windows password for $UserName (the account the deploy task runs as)"

    $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$deployScript`""
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    Register-ScheduledTask -TaskName $taskName -Action $action -Settings $settings `
        -User $cred.UserName -Password $cred.GetNetworkCredential().Password -RunLevel Limited -Force | Out-Null
    Write-Host "Registered $taskName."
}

$sid = (New-Object System.Security.Principal.NTAccount($UserName)).Translate([System.Security.Principal.SecurityIdentifier]).Value

# A stored-password task logs on as a batch job (logon type 4). Standard accounts
# lack SeBatchLogonRight by default, so the task fails in LogonUserExEx with
# 0xC000015B and never starts.
$tmp = Join-Path $env:TEMP 'deploy-task-rights'
New-Item -ItemType Directory -Force $tmp | Out-Null
secedit /export /cfg "$tmp\current.inf" /areas USER_RIGHTS | Out-Null
$line = Select-String -Path "$tmp\current.inf" -Pattern '^SeBatchLogonRight\s*=' | Select-Object -First 1
$holders = if ($line) { ($line.Line -split '=', 2)[1].Trim() } else { '' }
if ($holders -notmatch [regex]::Escape("*$sid")) {
    $holders = (@($holders, "*$sid") | Where-Object { $_ }) -join ','
    @('[Unicode]', 'Unicode=yes', '[Version]', 'signature="$CHICAGO$"', 'Revision=1',
      '[Privilege Rights]', "SeBatchLogonRight = $holders") | Set-Content "$tmp\batch.inf" -Encoding Unicode
    secedit /configure /db "$tmp\batch.sdb" /cfg "$tmp\batch.inf" /areas USER_RIGHTS | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "secedit failed to grant SeBatchLogonRight (exit $LASTEXITCODE)" }
}
Remove-Item -Recurse -Force $tmp
Write-Host "$UserName holds 'Log on as a batch job'."

$scheduler = New-Object -ComObject Schedule.Service
$scheduler.Connect()
$task = $scheduler.GetFolder('\').GetTask($taskName)
$dacl = $task.GetSecurityDescriptor(4)  # DACL only
$ace = "(A;;GRGX;;;$sid)"
if ($dacl -notlike "*$ace*") {
    $task.SetSecurityDescriptor($dacl + $ace, 0)
}
Write-Host "Granted $UserName read/run on $taskName. Trigger with: schtasks /run /tn $taskName"
