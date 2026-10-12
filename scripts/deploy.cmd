@echo off
rem Rebuilds and restarts the Docker stack. Run by the "revenue-console-deploy"
rem scheduled task so builds get Docker Desktop credentials even when triggered
rem over SSH (see "Docker builds over SSH" in CLAUDE.md). Output: deploy.log
cd /d "%~dp0.."
(
  echo === Deploy started %DATE% %TIME% ===
  docker compose build && docker compose up -d
  call echo === Deploy finished %%DATE%% %%TIME%% exit code %%ERRORLEVEL%% ===
) > deploy.log 2>&1
