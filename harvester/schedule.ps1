# VIRALFORGE Task Scheduler registration (PLAN.md Section 5 M1, cadence).
# Run from the repo root as Administrator. Adjust -RepoRoot if needed.
param(
    [string]$RepoRoot = (Get-Location).Path,
    [string]$Python = (Join-Path $RepoRoot ".venv\Scripts\python.exe")
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $Python)) { throw "venv python not found at $Python — run: python -m venv .venv" }

$tasks = @(
    @{ Name = "VF-Crawl";   Time = "06:00";  Args = "-m harvester.api_crawl --once" },
    @{ Name = "VF-Snap";    Time = "12:00";  Args = "-m harvester.api_crawl --snapshots" },
    @{ Name = "VF-Snap2";   Time = "18:00";  Args = "-m harvester.api_crawl --snapshots" },
    @{ Name = "VF-Deep";    Time = "07:00";  Args = "-m harvester.deep_crawl --top 50" },
    @{ Name = "VF-Snap3";   Time = "23:30";  Args = "-m harvester.api_crawl --snapshots" }
)

foreach ($t in $tasks) {
    $action  = New-ScheduledTaskAction -Execute $Python -Argument $t.Args -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
    Write-Host "Registered $($t.Name)"
}
Write-Host "Done. Weekly M3 re-mine: run 'python -m miner.report' manually or add a Sunday task."
