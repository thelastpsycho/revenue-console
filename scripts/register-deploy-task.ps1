# One-time setup: registers the "revenue-console-deploy" scheduled task that runs
# scripts\deploy.cmd with "Run whether user is logged on or not", which gives
# Docker Desktop's credential helper the DPAPI access SSH pubkey logins lack.
# Run locally at the machine (not over SSH); prompts for the Windows password in
# a dialog so it never lands in shell history. Registering a stored-password task
# needs admin rights, and "The Anvaya Bali" is a standard account, so this runs
# elevated (as an admin account) but registers the task for -UserName and grants
# that account read/run access - otherwise it can't trigger the task over SSH.
# -GrantOnly re-applies just the access grant to an existing task.
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
$scheduler = New-Object -ComObject Schedule.Service
$scheduler.Connect()
$task = $scheduler.GetFolder('\').GetTask($taskName)
$dacl = $task.GetSecurityDescriptor(4)  # DACL only
$ace = "(A;;GRGX;;;$sid)"
if ($dacl -notlike "*$ace*") {
    $task.SetSecurityDescriptor($dacl + $ace, 0)
}
Write-Host "Granted $UserName read/run on $taskName. Trigger with: schtasks /run /tn $taskName"
