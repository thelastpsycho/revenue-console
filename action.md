I've cloned this repo (branch: docker-production) onto this Windows machine
to run it as production. The Docker setup (backend/Dockerfile,
frontend/Dockerfile + nginx.conf, scripts/trigger_fast_pipeline.py,
scripts/Dockerfile, docker-compose.yml) is already committed on this branch
- see docs/allotment-cli.md's "Production (Docker)" section for how the
pieces fit together. Nothing here needs to be redesigned; I need help
actually standing it up on this machine and debugging whatever breaks.

Before building, three things need to exist locally that are gitignored
and don't come from the clone - walk me through getting each one in place,
asking me for the files/values you need:

1. backend/.env - the Mac has a working copy with APP_ACCESS_PIN,
   APP_SESSION_SECRET, PMS_USERNAME/PASSWORD, DEDGE_USERNAME/PASSWORD.
   I'll paste its contents or move the file over. Keep APP_SECURE_COOKIES=0.

2. backend/app/scraper/.dedge_profile/ - a persistent Chrome profile
   directory from the Mac holding an already-completed D-EDGE
   device-verification trust cookie. This must be copied into the same
   path here BEFORE the first docker compose up, or D-EDGE automation
   will hang waiting for a human to click an emailed verification code in
   a browser window that, headless, doesn't exist.

3. cloudflared/ directory at the repo root, with:
   - cloudflared/credentials.json (copied from the Mac's
     ~/.cloudflared/468abe3e-96b9-48da-a27f-e95118853dd2.json)
   - cloudflared/config.yml:
     tunnel: 468abe3e-96b9-48da-a27f-e95118853dd2
     credentials-file: /etc/cloudflared/credentials.json
     ingress:
       - hostname: console.krisnatha.com
         service: http://frontend:80
       - service: http_status:404

Also confirm first: Docker Desktop is installed with the WSL2 backend
enabled, and this machine's sleep setting is off (it needs to stay up
unattended).

Once those are in place:
- docker compose build
- docker compose up -d
- docker compose ps - backend/frontend should show healthy, scheduler/
  cloudflared running
- curl http://localhost:8080/api/health should return {"status":"healthy"}
- docker compose logs -f scheduler - should show it polling the backend,
  logging in, and streaming pipeline logs (it starts in safe/preview mode
  by default, no live pipeline runs until I explicitly set
  SCHEDULER_ARGS=--live --schedule-60 in a root .env)
- Trigger a D-EDGE-touching pipeline step and confirm no "New device
  detected" message shows up in the logs - that's the check that the
  copied .dedge_profile actually carried its trust over correctly
- From outside the LAN, confirm https://console.krisnatha.com loads and
  logs in

Help me get through this step by step, and if a build or container fails,
read the actual error/logs before guessing at a fix.
