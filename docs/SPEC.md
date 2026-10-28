# SPEC – Hangtime

Stand: 19.10.2026. Technische Spezifikation. Fachliche Grundlage ist das Konzept im Second Brain unter `02 Projekte/Hangtime/`.

---

## 1. Nutzerfluss

1. **Onboarding** (einmalig, unter 60 Sekunden)
   - Ziel wählen: `vertical_jump` | `sprint_speed` | `injury_resilience` | `general_athleticism`
   - Stand: Trainingsalter (Jahre Krafttraining), Einheiten pro Woche, Verletzungen (Freitext + Häkchen für Knie/Sprunggelenk/Rücken), verfügbares Equipment
   - Trainingsplan: Text einfügen **oder** Foto hochladen → wird strukturiert → Nutzer bestätigt oder korrigiert
2. **Übung prüfen**
   - Video hochladen (mp4/mov, max. 60 s, max. 100 MB)
   - Optional: Caption/Videobeschreibung aus der App einfügen (Freitext, max. 2.000 Zeichen). Enthält oft den eigentlichen Claim.
   - Fortschrittsanzeige mit den Pipeline-Schritten (sichtbar im Demo-Video)
3. **Ergebnis-Karte**
   - Stufe 1: Urteil (`well_supported` | `partly_supported` | `unsupported` | `myth`) + Begründung + geprüfte Quellen
   - Stufe 2: persönliche Passung (`good_fit` | `conditional` | `not_recommended`) + Begründung
   - Stufe 3: Tausch-Vorschlag mit **sichtbarem Plan-Diff** (alte Übung durchgestrichen, neue hervorgehoben, Volumen umgerechnet)
   - Button „Apply swap to next session“ → Plan wird aktualisiert

**Bewusst nicht (Hackathon):** Links von TikTok/Instagram automatisch auslesen (Instagram braucht Login, TikTok blockt Server-IPs, verstößt gegen die Nutzungsbedingungen; Stretch Goal siehe PLAN), YouTube-Download, Login, mehrere Nutzer, andere Ziele als Athletik.

---

## 2. Modelle und Routing

Alle IDs in `app/config.py` über Env-Variablen. Die Standardwerte unten stammen aus öffentlichen Listen und **müssen in M0 mit `scripts/check_models.py` gegen den eigenen Account geprüft werden** (`GET /v1/models`).

| Rolle | Env-Variable | Kandidat (prüfen!) | Aufgaben |
|---|---|---|---|
| Schnell | `MODEL_FAST` | `nvidia/Nemotron-3_5-Lightning` oder `nvidia/nemotron-3-nano-30b…` | Behauptung strukturieren, Übung zuordnen, Plan aus Text parsen, Evidenz-Karten vorsortieren |
| Vision | `MODEL_VISION` | `nvidia/Nemotron-3.5-Super-VL`, sonst Nemotron 3 Nano Omni oder Nano 2 VL | Einzelbilder verstehen inkl. eingeblendetem Text, Plan-Foto lesen |
| Reasoning | `MODEL_REASON` | `nvidia/Nemotron-3-Ultra-550b-a55b`, Fallback `nvidia/nemotron-3-super-120b-a12b` | Urteil, persönliche Passung, Begründung des Tauschs |
| Audio (optional) | `MODEL_AUDIO` | nur falls ein Nemotron-Omni-Modell Audio per API annimmt | Gesprochenes transkribieren |

**Video-Eingabe:** Token Factory nimmt laut Doku Bilder (`image_url`, URL oder base64), aber keine Videos. `MODEL_VISION` (Super-VL) nimmt laut M0-Test **max. 8 Bilder pro Aufruf** (12 → HTTP 400). Deshalb:

- **Kurze Videos (≤ 20 s):** `video.py` zieht mit ffmpeg **8 gleichmäßig verteilte Einzelbilder** (max. 768 px Kantenlänge, JPEG) übers ganze Video.
- **Längere Videos (> 20 s): Grob-Scan zuerst.** `scan.py` zieht **16 Bilder** übers ganze Video in niedriger Auflösung (max. 384 px) und schickt sie in **zwei Aufrufen à 8** an `MODEL_VISION` (der zweite bekommt die Namen aus dem ersten). Ergebnis: **alle Übungen** im Video, je mit den Bildern, auf denen sie ausgeführt werden, plus aller eingeblendeter Text (der Claim steht oft im Intro). Pro Übung ein Zeitfenster: längster zusammenhängender Bildblock + ein Bildabstand Puffer, **max. 8 s** (8 Bilder über 40 s verpassen jeden Sprung, Test 28.10.). Danach zieht `video.py` die 8 Bilder in voller Auflösung **nur aus diesem Fenster**.
- **Mehrere Übungen im Video (entschieden 28.10., Variante A):** analysiert wird die Hauptübung (die auf den meisten Scan-Bildern). Die anderen werden als „Also in this video“ angezeigt und lassen sich einzeln prüfen, ohne neuen Scan. Der Claim bezieht sich meist aufs ganze Video, das ist in Ordnung und wird im Urteil so benannt.
- Findet der Grob-Scan keine Übung: Fallback auf 8 Bilder übers ganze Video.

**Strukturierte Ausgabe:** `response_format={"type": "json_schema", "json_schema": {"name": ..., "schema": ..., "strict": true}}`. Schema zusätzlich in den System-Prompt schreiben (Empfehlung der Token-Factory-Doku). In M0 testen, welche Nemotron-Modelle JSON-Schema zuverlässig einhalten.

---

## 3. Pipeline

```
Video ──► video.py ──► understand.py ──► exercise.py ──┬──► evidence.py ──┐
                       (VISION)          (FAST)        │   (FAST+Tavily)  ├──► verdict.py ──► citations.py ──► Ergebnis
Profil + Plan (DB) ────────────────────────────────────┴──► swap.py ──────┘    (REASON)
```

| Schritt | Eingabe | Ausgabe | Modell |
|---|---|---|---|
| `scan.py` (nur > 20 s) | Videodatei | `CoarseScan` (alle Übungen mit Bildern, Bildtext) → `Segment`-Liste | VISION (2×) |
| `video.py` | Videodatei, optional Zeitfenster | 8 JPEG-Bilder, Dauer | – |
| `understand.py` | Bilder, Bildtext aus dem Grob-Scan | `VideoUnderstanding` | VISION |
| `exercise.py` | `VideoUnderstanding`, Caption (optional), Übungsliste (Namen + IDs) | `Claim` + `ExerciseProfile` (DB-Treffer oder `auto_profiled`) | FAST |
| `evidence.py` | `ExerciseProfile`, `Claim` | 1–5 `EvidenceCard`, ggf. Tavily-Treffer | FAST + Tavily |
| `swap.py` | `ExerciseProfile`, `TrainingPlan`, `UserProfile` | `SwapProposal` oder `null` | – (deterministisch) |
| `verdict.py` | alles oben | `Verdict` | REASON |
| `citations.py` | `Verdict`, Evidenz | bereinigtes `Verdict` | – |

`run.py` führt die Schritte aus, schreibt nach jedem Schritt den Status in SQLite. Das Frontend pollt `GET /api/analyses/{id}` per HTMX alle 1,5 s. Zielzeit für die ganze Analyse: unter 45 Sekunden.

### Evidenz-Auswahl (keine Vektordatenbank)
1. Vorfilter nach Tags: Karten, deren `exercise_tags` das `pattern` oder die `fv_zone` der Übung enthalten.
2. FAST-Modell wählt aus den Vorfilter-Treffern (nur Titel + Kurzfazit) die 1–5 relevantesten.
3. **Tavily nur, wenn weniger als 2 relevante Karten gefunden werden.** Suche mit `include_domains=["pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "journals.lww.com", "link.springer.com"]`, max. 5 Ergebnisse. Tavily-Treffer werden als `ExternalSource` (Titel, URL, Snippet) mitgegeben und im Urteil klar als „web source, not curated“ gekennzeichnet.

### Zitat-Prüfung (`citations.py`)
Jedes Element in `Verdict.citations` hat `source_id` und `quote`.
- `source_id` muss eine übergebene `EvidenceCard.id` oder `ExternalSource.id` sein.
- `quote` muss (nach Normalisierung von Leerzeichen und Groß-/Kleinschreibung) **wörtlich** in `key_findings`/`summary` der Karte oder im Snippet der externen Quelle vorkommen.
- Nicht bestanden → Zitat entfernen. Bleibt kein Zitat übrig → Urteil wird auf `unsupported` gesetzt mit Hinweis „No verifiable evidence found“.
- Anzahl entfernter Zitate wird geloggt (gute Zahl fürs README).

---

## 4. Datenmodelle (Pydantic, `app/models.py`)

Feldnamen englisch. Enums sind Pflicht, damit der Tausch-Algorithmus vergleichen kann.

```python
class Pattern(str, Enum):
    squat = "squat"; hinge = "hinge"; lunge = "lunge"
    jump_vertical = "jump_vertical"; jump_horizontal = "jump_horizontal"
    bound = "bound"; hop_unilateral = "hop_unilateral"; landing = "landing"
    calf_ankle = "calf_ankle"; sprint = "sprint"; core = "core"; other = "other"

class FVZone(str, Enum):           # Kraft-Geschwindigkeits-Kurve
    max_strength = "max_strength"
    strength_speed = "strength_speed"
    speed_strength = "speed_strength"
    reactive = "reactive"          # schneller Dehnungs-Verkürzungs-Zyklus

class SSC(str, Enum):  none = "none"; slow = "slow"; fast = "fast"
class Emphasis(str, Enum): eccentric="eccentric"; isometric="isometric"; concentric="concentric"; mixed="mixed"
class Resistance(str, Enum): bodyweight="bodyweight"; free_weight="free_weight"; band="band"; chain="chain"; machine="machine"
class HardestPoint(str, Enum): bottom="bottom"; mid="mid"; top="top"; even="even"
class Laterality(str, Enum): bilateral="bilateral"; unilateral="unilateral"
class Goal(str, Enum): vertical_jump="vertical_jump"; sprint_speed="sprint_speed"; injury_resilience="injury_resilience"; general_athleticism="general_athleticism"
class Rating(str, Enum): well_supported="well_supported"; partly_supported="partly_supported"; unsupported="unsupported"; myth="myth"
class Fit(str, Enum): good_fit="good_fit"; conditional="conditional"; not_recommended="not_recommended"
# Reihenfolge von FVZone und SSC definiert "benachbart" (Index-Abstand 1).

class LoadCost(BaseModel):
    fatigue: int            # 1–3
    joint_stress: int       # 1–3
    ground_contacts_per_rep: int   # 0 bei Kraftübungen

class ExerciseProfile(BaseModel):
    id: str                 # slug, z. B. "depth-jump"
    name: str
    aliases: list[str]
    pattern: Pattern
    laterality: Laterality
    fv_zone: FVZone
    ssc: SSC
    emphasis: Emphasis
    resistance: Resistance
    hardest_point: HardestPoint
    load_cost: LoadCost
    equipment: list[str]    # "none", "box", "barbell", "dumbbell", "band", ...
    min_training_age_years: float
    rep_min: int            # kein Tupel: strict JSON Schema verträgt Tupel schlecht
    rep_max: int
    contraindications: list[str]   # "knee_pain", "ankle_instability", ...
    evidence_card_ids: list[str]
    reviewed: bool = False
    auto_profiled: bool = False    # True = vom LLM für unbekannte Übung erzeugt

class EvidenceCard(BaseModel):
    id: str                 # z. B. "markovic-2007-plyo-meta"
    citation: str           # "Markovic G (2007). Does plyometric training improve ... Br J Sports Med."
    url: str                # DOI- oder PubMed-Link
    study_type: str         # "meta-analysis", "RCT", "review", ...
    population: str         # "trained male athletes, 18–25 y"
    intervention: str
    duration_weeks: int | None
    outcome_measures: list[str]   # "CMJ", "SJ", "DJ RSI", ...
    summary: str            # 2–3 Sätze, eigene Worte
    key_findings: list[str] # 2–5 kurze, prüfbare Aussagen (Grundlage der Zitat-Prüfung)
    effect_direction: str   # "positive" | "no_effect" | "mixed" | "negative"
    effect_size: str | None # wörtlich aus der Studie, falls berichtet
    exercise_tags: list[str]  # Pattern- und FVZone-Werte + Übungs-IDs
    evidence_path: str      # "direct" (misst Sprung/Sprint/Kraft) | "indirect" (Verletzung, Sehne, Schmerz, Verfügbarkeit)
    limitations: str
    reviewed: bool = False

class UserProfile(BaseModel):
    goal: Goal
    training_age_years: float
    sessions_per_week: int
    injuries: list[str]
    equipment: list[str]

class PlannedExercise(BaseModel):
    exercise_id: str | None   # None = nicht in DB erkannt
    raw_name: str
    sets: int
    reps: int
    load: str | None          # "70% 1RM", "bodyweight", "40 cm box"

class Session(BaseModel):
    id: str
    label: str                # "Tuesday – Lower power"
    weekday: int | None       # 0 = Montag
    exercises: list[PlannedExercise]

class TrainingPlan(BaseModel):
    sessions: list[Session]

class CoarseScan(BaseModel):
    exercise_frames: list[int]  # Indizes 0–7 der Bilder, auf denen die Übung läuft
    on_screen_text: list[str]   # sämtlicher eingeblendeter Text im ganzen Video
    multiple_exercises: bool

class VideoUnderstanding(BaseModel):
    movement_description: str
    on_screen_text: list[str]
    equipment_seen: list[str]
    execution_notes: str      # Tempo, Bodenkontakt, Tiefe, ...

class Claim(BaseModel):
    exercise_name: str
    promised_effect: str      # "+10 cm vertical in 2 weeks" oder "" wenn keins
    target_audience: str
    matched_exercise_id: str | None
    match_confidence: float

class SwapProposal(BaseModel):
    session_id: str
    replaces_exercise_id: str
    replaces_raw_name: str
    new_exercise_id: str
    old_prescription: str     # "3×6"
    new_prescription: str     # "3×5"
    similarity: float         # 0–1
    matched_on: list[str]     # ["pattern", "fv_zone", "ssc"]
    volume_note: str          # deterministisch erzeugt

class Citation(BaseModel):
    source_id: str
    quote: str

class Verdict(BaseModel):
    rating: Rating                    # well_supported | partly_supported | unsupported | myth
    headline: str                     # ein Satz
    reasoning: str                    # max. 4 Sätze
    citations: list[Citation]
    personal_fit: Fit                 # good_fit | conditional | not_recommended
    personal_fit_reason: str
    swap_explanation: str | None      # erklärt SwapProposal, erfindet nichts Neues
    safety_notes: list[str]
```

---

## 5. Tausch-Algorithmus (`swap.py`) – Entwurf, Titus prüft die Regeln

**Ziel:** Die neue Übung ersetzt in der **nächsten anstehenden Einheit** genau eine Übung mit möglichst gleichem Trainingsreiz und gleicher Belastung.

**Schritt 1 – Harte Filter (Kandidat fliegt raus, wenn …)**
- Equipment der neuen Übung ist beim Nutzer nicht vorhanden
- `min_training_age_years` der neuen Übung > Trainingsalter des Nutzers
- eine `contraindication` der neuen Übung steht in den Verletzungen des Nutzers
- Pattern-Familie passt nicht (Familien: {squat, lunge}, {hinge}, {jump_vertical, jump_horizontal, bound, hop_unilateral, landing}, {calf_ankle}, {sprint}, {core})

Fällt die neue Übung schon an den Nutzer-Filtern durch → kein Tausch, `personal_fit = not_recommended`, Grund wird an `verdict.py` übergeben.

**Schritt 2 – Ähnlichkeit (0–1) für jede Übung in der nächsten Einheit**

| Merkmal | Gewicht | Punkte |
|---|---|---|
| `fv_zone` | 0,30 | gleich = 1, benachbart = 0,5, sonst 0 |
| `pattern` | 0,25 | gleich = 1, gleiche Familie = 0,6 |
| `ssc` | 0,15 | gleich = 1, benachbart = 0,5 |
| `laterality` | 0,10 | gleich = 1 |
| `emphasis` | 0,10 | gleich = 1, eins davon `mixed` = 0,5 |
| Belastungsnähe | 0,10 | 1 − (|Δfatigue| + |Δjoint_stress|) / 4 |

Bester Kandidat mit Ähnlichkeit **≥ 0,60** wird Tauschpartner. Darunter: kein Tausch, Hinweis „no equivalent slot in your plan“. Bei Gleichstand: Übung mit höherer Belastung wird ersetzt (konservativ).

Nächste Einheit: erste Session mit `weekday` ≥ heute, sonst erste Session im Plan.

**Schritt 3 – Volumen umrechnen**
- Sätze bleiben gleich.
- Bei Sprung-/Plyo-Übungen: gleiche Gesamt-Bodenkontakte. `new_reps = round(old_reps × old_gc / new_gc)`.
- Sonst: gleiche Gesamt-Ermüdung. `new_reps = round(old_reps × old_fatigue / new_fatigue)`.
- Ergebnis auf `rep_min`–`rep_max` der neuen Übung begrenzen.
- `volume_note` wird aus diesen Zahlen als fester Satz erzeugt, nicht vom LLM.

**Pflicht-Tests (`tests/test_swap.py`):** mindestens 8 Fälle, die Titus vorgibt, z. B. „Depth Jump ersetzt Box Jump, nicht Back Squat“, „Single-Leg Hop wird bei Sprunggelenk-Instabilität abgelehnt“.

---

## 6. Prompts (Kern, englisch)

- **scan (VISION, nur > 20 s, 2 Aufrufe):** „You see 8 low-resolution frames from part {part} of 2 of a fitness video, in order, indices 0-7. List every different exercise that is actually being performed (not talking, intro, outro or a static pose), each with the indices of the frames that show it. Use short common exercise names. Transcribe all on-screen text exactly, from every frame.“ Teil 2 bekommt zusätzlich die Namen aus Teil 1.
- **understand (VISION):** „You see 8 frames from a short fitness video in order. Describe the movement precisely (start position, action, landing, tempo, ground contact time if visible). Transcribe all on-screen text exactly. List equipment. Do not judge the exercise.“
- **exercise (FAST):** bekommt `VideoUnderstanding`, die optionale Caption und die Liste `id: name, aliases`. „Identify the exercise and the claim. The claim may be in the on-screen text, the caption, or both; prefer the most specific promise. If it matches a known exercise, return its id. Otherwise return null and fill a full ExerciseProfile.“
- **verdict (REASON):** bekommt Claim, Profil, Evidenz-Karten (nur `id`, `citation`, `summary`, `key_findings`, `limitations`), externe Quellen, UserProfile, Ergebnis von `swap.py`. Regeln im Prompt: „Only cite by source_id. Every quote must be copied verbatim from key_findings, summary or snippet. Do not invent studies. Explain the given swap; never propose a different swap. Be direct, max. 4 sentences reasoning. If evidence is thin, say so. Evidence marked indirect (injury prevention, tendon health, pain, availability) can support a long-term benefit, never a specific performance promise such as '+10 cm in 4 weeks'.“

---

## 7. API

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Startseite / Onboarding oder Dashboard |
| POST | `/api/profile` | Profil speichern |
| POST | `/api/plan/parse` | Text oder Bild → `TrainingPlan`-Entwurf |
| PUT | `/api/plan` | bestätigten Plan speichern |
| POST | `/api/analyses` | Video hochladen (+ optional `caption`) → `{id}` |
| GET | `/api/analyses/{id}` | Status + Teilergebnisse (HTMX-Partial) |
| POST | `/api/analyses/{id}/apply-swap` | Tausch in den Plan übernehmen |
| GET | `/api/exercises` | Übungsdatenbank |
| GET | `/healthz` | Health-Check für Nebius |

Session: anonymes Cookie `ht_session`, alles in SQLite unter dieser ID. Für das Demo-Video: Route `/demo` lädt ein vorbereitetes Profil + Plan.

---

## 8. Daten

- `data/exercises.json`: 60–90 Übungen (Stand 23.10.: 82) für Sprungkraft/Athletik. Entwurf per `scripts/seed_exercises.py` (LLM), dann Prüfung durch Titus.
- `data/evidence_cards/*.json`: eine Datei pro Studie. Erzeugt per `scripts/ingest_studies.py data/raw/<datei>.pdf` (PDF-Text → FAST/REASON-Modell → Karte mit `reviewed: false`). Titus prüft jede Karte. Quelle: `Titus KI Brain/Archiv/pausiert/Jump-Trainer RAG/Korpus/` (Stand 20.10.: 14 PDFs + 2 Abstract-Notizen). Ziel: diese Studien + so viele zusätzliche, wie bis M2 geprüft werden können.
- `eval/testset.yaml`: 15–20 Einträge `{video, expected_rating, expected_fit, expected_swap_replaces, notes}`. Videos lokal, nicht im Repo.

---

## 9. Deployment

- `Dockerfile` auf Basis `python:3.12-slim` + `ffmpeg`, Start mit `uvicorn` auf Port 8000.
- Nebius Serverless Endpoint mit CPU-Instanz (Modelle laufen auf Token Factory, nicht im Container).
- Secrets als Env: `NEBIUS_API_KEY`, `TAVILY_API_KEY`, Modell-IDs.
- SQLite auf persistentem Volume, falls verfügbar. Sonst akzeptabel: Daten gehen bei Neustart verloren, `/demo` lädt Beispieldaten neu.

---

## 10. Offene Punkte

- [ ] Exakte Modell-IDs und JSON-Schema-Tauglichkeit (M0)
- [x] Nimmt das Vision-Modell 12 Bilder in einem Aufruf? Nein, max. 8 → 8 Einzelbilder + Grob-Scan bei > 20 s (entschieden 23.10.)
- [ ] Persistentes Volume auf Nebius Serverless Endpoints verfügbar?
- [ ] Regeln und Gewichte des Tausch-Algorithmus von Titus bestätigt
- [x] Name der App: Hangtime
