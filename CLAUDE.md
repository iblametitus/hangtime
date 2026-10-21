# CLAUDE.md – Hangtime

Diese Datei liest Claude Code zu Beginn jeder Session. Sie beschreibt, worum es geht und nach welchen Regeln gebaut wird.

**Einordnung:** Liegt im Code Brain unter `hackathons/2026-10 Nebius x NVIDIA/hangtime/`. Es gelten zusätzlich `../../../CLAUDE.md` (Code Brain) und die Root-`CLAUDE.md`. Als Ausnahme laut Code-Brain-Regel ist Hangtime **von Anfang an ein eigenes, öffentliches Git-Repo** auf GitHub. Im Code-Brain-Repo ist der Ordner per `.gitignore` ausgeschlossen. **Alles, was committet wird, ist sofort öffentlich:** vor jedem Push prüfen, dass keine `.env`, Keys, Studien-PDFs oder Videos dabei sind.
Hackathon-Unterlagen (Ausschreibung, Idee, Start-Prompt) liegen eine Ebene höher. Das Konzept liegt im Second Brain unter `02 Projekte/Hangtime/`.

## Worum es geht

Hangtime ist ein „schlauerer Trainingspartner“ für Sprungkraft und Athletik. Der Nutzer schickt ein Video einer Übung (z. B. aus TikTok oder Instagram). Hangtime antwortet in drei Stufen:

1. **Allgemein:** Taugt die Übung was? Evidenz-Urteil mit geprüften Quellen.
2. **Für dich:** Passt sie zu Ziel, Stand und Plan des Nutzers?
3. **Tausch-Vorschlag:** Welche Übung im nächsten Training kann ersetzt werden, ohne den Plan durcheinanderzubringen, inklusive umgerechnetem Volumen.

Einreichung beim **Nebius x NVIDIA Global AI Hackathon**, Track „Best Apps & Agents“, Bonus „Best Use of Tavily“.
**Deadline: Freitag, 30. Oktober 2026, 18:00 Uhr deutscher Zeit (10:00 PT).** Kein fester Zeitplan: so viel wie geht, so schnell wie geht, Meilensteine in der Reihenfolge aus `docs/PLAN.md`.

Die vollständige Spezifikation steht in `docs/SPEC.md`, der Bauplan mit Meilensteinen in `docs/PLAN.md`.

## Pflichtanforderungen des Hackathons (nie verletzen)

- Jede Analyse macht **echte Laufzeit-Aufrufe an Nebius Token Factory** (OpenAI-kompatibel, `https://api.tokenfactory.nebius.com/v1/`).
- Es wird **mindestens ein NVIDIA-Open-Source-Modell** genutzt (Nemotron). Alle LLM-Aufrufe laufen über Nemotron-Modelle.
- Repo ist **öffentlich** und hat eine **MIT-Lizenz** im Root.
- README auf **Englisch** mit Setup-Anleitung und Abschnitt, wo Nemotron, Token Factory, Nebius Serverless und Tavily eingesetzt werden.
- Alles, was Nutzer oder Jury sehen (UI-Texte, README, Fehlermeldungen), ist **auf Englisch**. Interne Doku in `docs/` darf deutsch sein.

## Stack

- Python 3.12, FastAPI, Pydantic v2, `openai`-SDK (für Token Factory), `tavily-python`
- Frontend: Jinja2-Templates + HTMX + Tailwind per CDN, mobile-first. Kein separates JS-Framework.
- Speicher: SQLite (eine Datei), anonyme Session per Cookie, kein Login
- Videoverarbeitung: `ffmpeg` (Einzelbilder ziehen)
- Deployment: Docker-Container auf **Nebius Serverless Endpoints**
- Tests: `pytest`

## Befehle

```bash
uv sync                                  # Abhängigkeiten
uv run uvicorn app.main:app --reload     # lokal starten
uv run pytest                            # Tests
uv run python scripts/check_models.py    # verfügbare Token-Factory-Modelle prüfen
uv run python scripts/eval.py            # Testset durchlaufen lassen
```

## Arbeitsregeln

1. **Halte dich an `docs/PLAN.md`.** Arbeite Meilenstein für Meilenstein. Neue Features außerhalb des Plans nur nach Rückfrage bei Titus.
2. **Modell-IDs stehen nur in `app/config.py`** (aus Umgebungsvariablen). Nie im Code hart verdrahten.
3. **Jeder LLM-Aufruf liefert strukturiertes JSON** über `response_format: json_schema`, abgeleitet aus den Pydantic-Modellen in `app/models.py`. Antworten werden immer mit Pydantic validiert. Bei Validierungsfehler: einmal erneut versuchen, dann sauberer Fehler.
4. **Der Tausch-Algorithmus (`app/pipeline/swap.py`) ist deterministisch** und enthält keinen LLM-Aufruf. Er hat Unit-Tests. Gleiche Eingabe → gleiches Ergebnis.
5. **Keine Quelle ohne Prüfung.** Jedes Zitat im Urteil läuft durch `app/pipeline/citations.py`. Was nicht nachweisbar ist, fliegt raus.
6. **Fachliche Inhalte gehören Titus.** Übungsprofile und Evidenz-Karten erzeugst du als Entwurf mit `"reviewed": false`. Nur Titus setzt `"reviewed": true`. Ändere geprüfte Einträge nicht ohne Rückfrage.
7. **Keine Studien-PDFs im Repo.** Originale liegen in `data/raw/` (in `.gitignore`). Ins Repo kommen nur Evidenz-Karten mit eigenen Zusammenfassungen und Quellenangabe.
8. **Die App ist immer demofähig.** Nach jedem Meilenstein: Tests grün, lokal lauffähig, Commit und Push. Ab Meilenstein M0 bleibt ein Deployment auf Nebius live.
9. **Vor dem Neubauen in `Code Brain/BAUSTEINE.md` nachsehen.** Relevant: `Archiv/pausiert/Jump-Trainer RAG/app` (PDF-Ingest und Quellen-RAG) und `Archiv/pausiert/Jump-Trainer App`. Nur als Referenz lesen, benötigte Teile hierher kopieren.
10. **Einfach vor clever.** Keine Vektordatenbank, keine Queue, keine Microservices. Eine FastAPI-App, eine SQLite-Datei.
11. Commit-Nachrichten auf Englisch, kurz, im Imperativ (öffentliches Repo).
12. Diese Datei und alle Dateien im Repo sind öffentlich. Keine privaten oder beruflichen Informationen hineinschreiben. Private Regeln stehen in den CLAUDE.md-Dateien der übergeordneten Ordner, die Claude Code automatisch mitliest.

## Projektstruktur

```
app/
  main.py            FastAPI-App, Routen, Templates
  config.py          Einstellungen und Modell-IDs aus Env
  models.py          alle Pydantic-Schemas (siehe SPEC.md)
  llm.py             Token-Factory-Client, JSON-Schema-Helper, Retry
  storage.py         SQLite
  tavily_client.py
  pipeline/
    video.py         Video → Einzelbilder (+ optional Audio)
    understand.py    Einzelbilder → Beschreibung + Behauptung (Vision-Modell)
    exercise.py      Behauptung → Übungsprofil (DB-Treffer oder neu)
    evidence.py      passende Evidenz-Karten finden, ggf. Tavily
    swap.py          Tausch-Algorithmus (deterministisch)
    verdict.py       Urteil und Erklärung (Reasoning-Modell)
    citations.py     Zitat-Prüfung
    plan_intake.py   Plan aus Text oder Foto
    run.py           orchestriert die Pipeline, schreibt Fortschritt
  templates/  static/
data/
  exercises.json
  evidence_cards/*.json
  raw/               (gitignored) Studien-PDFs
scripts/
  check_models.py  ingest_studies.py  seed_exercises.py  eval.py
eval/
  testset.yaml       echte Drill-Videos mit Titus' erwartetem Urteil
tests/
docs/
  SPEC.md  PLAN.md
```
