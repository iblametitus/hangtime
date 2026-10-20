# Deploy auf Nebius Serverless (M0)

Voraussetzung: Nebius-CLI ist installiert und eingeloggt (`nebius profile create`, läuft nur unter
Linux/macOS bzw. WSL2 — siehe `../../../CLAUDE.md`-Routinen-Historie / Dev-Log 2026-10-20).
Docker ist installiert (im WSL2-Ubuntu: `sudo apt install docker.io` oder Docker Desktop mit WSL2-Integration).

## 1. Projekt und Region setzen

```bash
nebius profile create                       # Browser-Login, Tenant/Projekt auswählen
nebius config set parent-id <PROJECT_ID>     # falls nicht schon beim Login gesetzt
export REGION_ID=eu-north1                   # oder die Region des Projekts
```

## 2. Container Registry anlegen (einmalig)

```bash
export REGISTRY_PATH=$(nebius registry create \
  --name gym-buddy \
  --format json | jq -r ".metadata.id" | cut -d- -f 2)
```

## 3. Image bauen und pushen

```bash
nebius iam get-access-token | docker login "cr.${REGION_ID}.nebius.cloud" \
  --username iam --password-stdin

export IMAGE="cr.${REGION_ID}.nebius.cloud/${REGISTRY_PATH}/gym-buddy:latest"
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

## 4. Endpoint anlegen

CPU reicht (die Modelle laufen auf Token Factory, nicht im Container):

```bash
nebius ai endpoint create \
  --name gym-buddy \
  --image "$IMAGE" \
  --platform cpu-e2 \
  --container-port 8000/http \
  --env "NEBIUS_API_KEY=${NEBIUS_API_KEY}" \
  --env "TAVILY_API_KEY=${TAVILY_API_KEY}" \
  --env "MODEL_FAST=${MODEL_FAST}" \
  --env "MODEL_VISION=${MODEL_VISION}" \
  --env "MODEL_REASON=${MODEL_REASON}" \
  --public \
  --auth none
```

`--container-port 8000/http` bekommt automatisch eine verwaltete `https://`-URL (siehe
[Nebius-CLI-Referenz](https://docs.nebius.com/cli/reference/ai/endpoint/create)). Die Modell-IDs erst
eintragen, nachdem `scripts/check_models.py` sie bestätigt hat.

## 5. Prüfen

```bash
curl https://<vergebene-endpoint-url>/healthz
```

Erwartet: `{"status":"ok"}`. Damit ist M0-Abnahmekriterium 4 erfüllt.

## Quellen
- [nebius ai endpoint create – CLI-Referenz](https://docs.nebius.com/cli/reference/ai/endpoint/create)
- [Container Registry Quickstart](https://docs.nebius.com/container-registry/quickstart)
- [Managing endpoints in Serverless AI](https://docs.nebius.com/serverless/endpoints/manage)
