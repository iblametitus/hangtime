# PLAN – Gym Buddy

**Abgabe: Freitag, 30.10.2026, 18:00 Uhr deutscher Zeit.** Kein fester Zeitplan: Die Meilensteine werden der Reihe nach so schnell wie möglich abgearbeitet.
Einzige Regel zur Zeit: Video, README und Einreichung (M8) brauchen erfahrungsgemäß ein bis zwei Tage. Sie dürfen nicht hinten runterfallen.

Jeder Meilenstein gilt erst als fertig, wenn alle Abnahmekriterien erfüllt sind, die Tests grün sind und committet und gepusht wurde.
„Titus“ = Aufgabe, die nur Titus erledigen kann.

**Repo:** Gym Buddy ist von Anfang an ein **eigenes, öffentliches Git-Repo** auf GitHub. Der Ordner liegt im Code Brain, ist dort aber per `.gitignore` ausgeschlossen.

---

## M0 – Fundament und Risiko-Check

Ziel: Alle technischen Unbekannten sind geklärt, eine leere App ist auf Nebius live, das Repo ist öffentlich.

- `git init` im Ordner `gym-buddy`, eigene `.gitignore` (mindestens `.env`, `.venv/`, `__pycache__/`, `data/raw/`, `*.db`, Videos)
- Öffentliches GitHub-Repo `gym-buddy` anlegen, Remote setzen, erster Push
- **Vor jedem Push prüfen:** keine `.env`, keine Keys, keine Studien-PDFs, keine Videos im Commit
- MIT-Lizenz im Root, Struktur aus `CLAUDE.md`
- `scripts/check_models.py`: listet alle Modelle des Accounts, testet für jeden Nemotron-Kandidaten
  1. einen JSON-Schema-Aufruf,
  2. beim Vision-Kandidaten einen Aufruf mit 12 Bildern.
- `app/llm.py` mit JSON-Schema-Helper und Retry
- Dockerfile, Deployment auf Nebius Serverless Endpoint, `/healthz` erreichbar

**Abnahme**
- [ ] Repo öffentlich auf GitHub, Lizenz im About-Bereich sichtbar
- [ ] `check_models.py` gibt eine Tabelle aus: Modell-ID, JSON ok, Vision ok, Latenz
- [ ] `.env.example` enthält die bestätigten Modell-IDs (ohne Keys)
- [ ] Öffentliche URL antwortet auf `/healthz`

**Titus:** Nebius-API-Key und Tavily-Key in `.env` eintragen. GitHub-Login für den ersten Push. Studien-PDFs aus `Archiv/pausiert/Jump-Trainer RAG/Korpus/` nach `data/raw/` kopieren. Mit dem Sammeln der Testset-Videos beginnen.

---

## M1 – Datenmodelle und Übungsdatenbank

- Alle Schemas aus SPEC Abschnitt 4 in `app/models.py`
- `scripts/seed_exercises.py` erzeugt 60–80 Übungsprofile als Entwurf
- Kleine Prüf-Seite `/admin/exercises`: Tabelle aller Übungen mit Filter, Bearbeiten, Häkchen „reviewed“ (spart Titus Zeit beim Prüfen)

**Abnahme**
- [ ] `data/exercises.json` validiert gegen das Schema
- [ ] Prüf-Seite funktioniert lokal

**Titus:** Übungsprofile prüfen und korrigieren. Mindestens alle Übungen, die im Demo-Plan und in den Testset-Videos vorkommen.

---

## M2 – Evidenz-Karten

- `scripts/ingest_studies.py`: PDF → Text → Evidenz-Karte (`reviewed: false`)
- Lauf über alle Studien in `data/raw/`
- Prüf-Seite `/admin/evidence` analog zu M1
- `app/pipeline/evidence.py` mit Tag-Vorfilter, FAST-Auswahl und Tavily-Fallback
- `app/pipeline/citations.py` mit Tests

**Abnahme**
- [ ] Alle Studien als Karten vorhanden
- [ ] `tests/test_citations.py`: erfundenes Zitat wird entfernt, wörtliches bleibt
- [ ] Tavily-Fallback greift bei einer Übung ohne passende Karte

**Titus:** Karten prüfen. Weitere Studien nur hinzufügen, wenn sie auch geprüft werden können.

---

## M3 – Video verstehen

- `video.py` (ffmpeg, 12 Bilder), `understand.py` (VISION), `exercise.py` (FAST)
- CLI: `uv run python -m app.pipeline.run_cli video.mp4` gibt `VideoUnderstanding`, `Claim` und `ExerciseProfile` aus

**Abnahme**
- [ ] Für 5 Testset-Videos wird die Übung korrekt erkannt
- [ ] Eingeblendeter Text wird ausgelesen

**Titus:** Mindestens 10 Testset-Videos mit erwartetem Urteil in `eval/testset.yaml`.

---

## M4 – Plan, Profil und Tausch

- `plan_intake.py`: Text → Plan (FAST), Foto → Plan (VISION), Zuordnung zu Übungs-IDs
- Profil- und Plan-Speicherung in SQLite
- `swap.py` exakt nach SPEC Abschnitt 5
- `tests/test_swap.py` mit den Fällen von Titus

**Abnahme**
- [ ] Foto eines handgeschriebenen Plans → korrekt strukturierter Plan
- [ ] Alle Swap-Tests grün

**Titus:** 8 Swap-Testfälle formulieren („wenn X geschickt wird und der Plan Y enthält, soll Z ersetzt werden, weil …“). Gewichte und Regeln in SPEC Abschnitt 5 bestätigen oder ändern.

---

## M5 – Urteil und End-to-End

- `verdict.py` (REASON) + Zitat-Prüfung im Ablauf
- `run.py` orchestriert alles mit Statusupdates
- `scripts/eval.py` läuft über das Testset und vergleicht mit Titus' Erwartung

**Abnahme**
- [ ] Ein Video läuft komplett durch und liefert ein gültiges `Verdict` in unter 45 Sekunden
- [ ] `eval.py` gibt Trefferquote für Rating, Fit und Swap aus

---

## M6 – Oberfläche und Deployment

- Screens: Onboarding, Plan-Ansicht, Upload mit Fortschrittsschritten, Ergebnis-Karte mit Plan-Diff, „Apply swap“
- Mobile-first, englische Texte
- `/demo`-Route mit vorbereitetem Profil und Plan
- Deployment der vollständigen App auf Nebius

**Abnahme**
- [ ] Auf dem Handy über die öffentliche URL komplett durchspielbar
- [ ] Plan-Diff ist auf einen Blick verständlich

---

## M7 – Qualität

- `eval.py` über alle 15–20 Testset-Videos, schlechteste Fälle analysieren und Prompts/Daten verbessern
- Fehlerfälle sauber abfangen (kein Video, unbekannte Übung, Timeout)
- Optional, nur wenn alles andere fertig ist: teilbare Ergebnis-Karte als Bild

**Abnahme**
- [ ] Eval-Ergebnis notiert (Zahl fürs README und Video)
- [ ] Kein unbehandelter Fehler beim Durchspielen des Demo-Ablaufs

---

## M8 – Einreichungs-Material

- README (englisch): Problem, Demo-Link, Video-Link, Architektur-Diagramm, Setup, „How we use Nemotron / Token Factory / Nebius Serverless / Tavily“, Eval-Ergebnis, Lizenz
- Devpost-Projektbeschreibung (englisch)
- Feedback-Text zu Token Factory, AI Cloud und NVIDIA-Modellen (konkret, mit Beispielen – es gibt 10 Feedback-Preise)
- Demo-Video unter 3 Minuten, öffentlich auf YouTube, ohne geschützte Musik
- Letzte Kontrolle: Demo-URL, Repo öffentlich, Lizenz sichtbar, Video öffentlich
- Einreichung auf Devpost vor 18:00 Uhr am 30.10.

---

## Wenn es eng wird – Streichliste in dieser Reihenfolge

1. Teilbare Ergebnis-Karte als Bild
2. Foto-Eingabe für den Plan (Text bleibt)
3. Admin-Seiten (Prüfen direkt in den JSON-Dateien)
4. Tavily-Fallback (nur kuratierte Karten) – kostet die Chance auf den Tavily-Bonus

**Nie streichen:** Tausch-Vorschlag mit Plan-Diff, Zitat-Prüfung, Live-Deployment, Video.
