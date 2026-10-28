# Deploy (Render)

Live: https://hangtime-88yw.onrender.com (`/healthz` → `{"status":"ok"}`)

Hangtime läuft als kostenloser Docker-Web-Service auf Render. Die Modelle laufen auf
Nebius Token Factory, der Container braucht nur CPU.

## Wie es aufgesetzt ist
- `render.yaml` (Blueprint) beschreibt den Service: Docker, Free-Plan, Frankfurt, Health-Check `/healthz`.
- Erstmalig über https://render.com/deploy?repo=https://github.com/iblametitus/hangtime angelegt,
  `NEBIUS_API_KEY` und `TAVILY_API_KEY` im Render-Dashboard eingetragen (nicht im Repo).
- Jeder Push auf `main` löst automatisch einen neuen Deploy aus.

## Hinweise
- Free-Plan schläft nach 15 min ohne Traffic. Erster Aufruf danach braucht ca. 30–60 s.
  Vor einer Live-Demo die URL einmal aufrufen.
- Admin-Seiten sind öffentlich aus (`ENABLE_ADMIN` nicht gesetzt).

## Warum nicht Nebius AI Cloud / Hugging Face
- Nebius AI Cloud: neuer Tenant ist gesperrt, bis eine Karte hinterlegt ist (25 $ Vorauszahlung).
  Nicht nötig, weil die Hackathon-Pflicht über Token Factory erfüllt ist. Altes Runbook:
  `DEPLOY-nebius-cloud.md`.
- Hugging Face: Docker Spaces brauchen inzwischen ein PRO-Abo.

## Lokal / Codespace testen
Lokal fehlt ffmpeg. Der GitHub Codespace (`.devcontainer/`) hat Docker:
`docker build -t hangtime . && docker run -p 8000:8000 --env-file .env hangtime`
