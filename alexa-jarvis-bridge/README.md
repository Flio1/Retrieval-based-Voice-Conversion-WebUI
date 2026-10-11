# Alexa → JARVIS Voice Bridge

Ein **Custom Alexa Skill**, der gesprochene Befehle von einem beliebigen Echo‑Gerät
(inkl. **Echo Spot 2024**) entgegennimmt, sie an deine **JARVIS**-Instanz weiterreicht
und die Antwort von JARVIS als Sprache zurückgibt.

> **Wichtig / ehrlich:** Das ist eine **Sprach**-Brücke (Voice in → Voice out).
> Es ist **kein** Bildschirm‑Mirroring. Der Echo Spot hat keinen Weg, ein Handy‑Bild
> darzustellen – das ist eine Hardware-/Plattform­grenze, kein Skill kann das ändern.

---

## Architektur

```
 ┌──────────┐   Sprache    ┌──────────────┐   HTTPS/JSON   ┌───────────────┐
 │ Echo Spot│ ───────────▶ │ Alexa Cloud  │ ─────────────▶ │  Dieser Skill │
 │ (du)     │ ◀─────────── │ (ASR + TTS)  │ ◀───────────── │  (Handler)    │
 └──────────┘   Antwort    └──────────────┘    Antwort     └──────┬────────┘
                                                                  │ HTTP(S) POST
                                                                  ▼
                                                          ┌───────────────┐
                                                          │   JARVIS       │
                                                          │ (jarvis_*.py)  │
                                                          └───────────────┘
```

Der Handler ist **frameworklos** (nur Python‑Stdlib) und läuft an zwei Orten:

- **AWS Lambda** (empfohlen – Amazon validiert die Request‑Signatur automatisch), oder
- **selbst gehostet** über `lambda/local_server.py` hinter einem HTTPS‑Tunnel.

---

## Schnellster Weg — ein Befehl (empfohlen)

Als **Alexa‑hosted Skill**: Amazon stellt die Lambda kostenlos bereit, du brauchst
**kein AWS‑Konto**. Nur Node.js + ASK CLI, dann:

```bash
npm install -g ask-cli      # einmalig
cd alexa-jarvis-bridge
./deploy.sh                 # öffnet beim ersten Mal den Amazon-Login
```

Der **einzige** manuelle Schritt ist der einmalige Browser‑Login in **dein** Amazon‑Konto
(dasselbe, auf dem dein Echo registriert ist). Das kann niemand übernehmen, weil der
Skill in dein Konto deployt wird. Danach läuft alles automatisch.

Der Skill **funktioniert sofort — auch ohne JARVIS**: Solange `JARVIS_ENDPOINT` nicht
gesetzt ist, bestätigt er nur, was er verstanden hat. Sobald du die JARVIS‑Adresse
hinterlegst, leitet er alles weiter.

---

## Dateien

| Datei | Zweck |
|---|---|
| `deploy.sh` | Ein‑Befehl‑Deploy (Alexa‑hosted, kein AWS‑Konto nötig) |
| `ask-resources.json` | ASK‑CLI‑Projektkonfiguration |
| `skill-package/skill.json` | Skill‑Manifest (Name, Locale, privat) |
| `skill-package/interactionModels/custom/de-DE.json` | Interaction Model (Invocation, Intents, deutsche Utterances) |
| `lambda/handler.py` | Kernlogik: Alexa‑Request → JARVIS → Alexa‑Response (Stdlib‑only) |
| `lambda/lambda_function.py` | Lambda‑Einstiegspunkt (auch für Alexa‑hosted) |
| `lambda/local_server.py` | Optionaler Selbst‑Hosting‑Server (Test / Tunnel) |
| `.env.example` | Vorlage für die Konfiguration |
| `requirements.txt` | Keine Pflicht‑Abhängigkeiten (Stdlib reicht) |

---

## JARVIS‑Vertrag (die eine Sache, die du anpassen musst)

Der Skill schickt an `JARVIS_ENDPOINT` ein **POST** mit JSON:

```json
{
  "text": "wie ist das wetter morgen",
  "source": "alexa",
  "locale": "de-DE",
  "session_id": "amzn1.echo-api.session....",
  "intent": "AskJarvisIntent"
}
```

und erwartet als Antwort JSON mit **einem** dieser Felder (in dieser Reihenfolge geprüft):

```json
{ "reply": "Morgen wird es sonnig bei 14 Grad." }
```

`reply` → `speech` → `text` werden akzeptiert. Optional:
`{ "end_session": true }` beendet die Alexa‑Sitzung nach der Antwort.

> In JARVIS brauchst du also nur einen kleinen HTTP‑Endpoint, der `text` nimmt,
> es durch deine IntentEngine schickt und `{"reply": "..."}` zurückgibt.

---

## Setup (manueller Weg — nur falls du *nicht* `deploy.sh` nutzt)

### 1. Skill anlegen
1. [developer.amazon.com/alexa/console/ask](https://developer.amazon.com/alexa/console/ask) → **Create Skill**
2. Model: **Custom**, Hosting: **Provision your own** (Lambda/eigener Endpoint)
3. Im Reiter **Build → Interaction Model → JSON Editor** den Inhalt von
   `skill-package/interactionModels/custom/de-DE.json` einfügen → **Save** → **Build Model**

### 2a. Backend auf AWS Lambda
```bash
cd lambda
zip -r ../jarvis-bridge.zip handler.py lambda_function.py
# In AWS Lambda: Python 3.12, Handler = lambda_function.lambda_handler
# Trigger: "Alexa Skills Kit" + deine Skill-ID eintragen
# Env-Variablen setzen (siehe .env.example)
```
Im Skill unter **Endpoint** → *AWS Lambda ARN* den ARN eintragen.

### 2b. Backend selbst hosten (z. B. neben JARVIS)
```bash
cp .env.example .env    # und ausfüllen
set -a; source .env; set +a
python lambda/local_server.py        # lauscht auf :8088
```
Alexa verlangt einen **öffentlich erreichbaren HTTPS‑Endpoint mit gültigem Zertifikat**.
Dafür einen Tunnel/Reverse‑Proxy davor setzen, z. B.:
```bash
cloudflared tunnel --url http://localhost:8088
# oder: ngrok http 8088
```
Die HTTPS‑URL dann im Skill unter **Endpoint → HTTPS** eintragen
(Zertifikatstyp: „My development endpoint has a certificate from a trusted CA").

### 3. Testen
- Entwickler‑Konsole → **Test** → auf *Development* stellen.
- „Alexa, öffne mein jarvis" → danach z. B. „frag nach dem wetter".
- Oder direkt am Echo Spot (gleiches Amazon‑Konto wie der Dev‑Account).

---

## Konfiguration (Env)

| Variable | Pflicht | Beschreibung |
|---|---|---|
| `JARVIS_ENDPOINT` | ja | URL deines JARVIS‑HTTP‑Endpoints |
| `JARVIS_API_KEY` | nein | wird als `Authorization: Bearer <key>` mitgeschickt |
| `JARVIS_TIMEOUT` | nein | Sekunden bis Timeout (Default 7 – Alexa bricht bei ~8s ab) |
| `ALEXA_SKILL_ID` | empfohlen | nur Requests dieser Skill‑ID werden akzeptiert |

---

## Sicherheit

- **Skill‑ID‑Prüfung**: Mit gesetzter `ALEXA_SKILL_ID` lehnt der Handler fremde Requests ab.
- **Lambda** validiert die Alexa‑Request‑Signatur selbst – der sicherste Weg.
- **Selbst gehostet**: `local_server.py` prüft die Alexa‑Signatur **nicht** vollständig.
  Betreibe ihn nur hinter einem vertrauenswürdigen Tunnel und mit gesetzter `ALEXA_SKILL_ID`.
  Für den Produktivbetrieb entweder Lambda nutzen oder eine echte Signaturprüfung ergänzen.
- Lege **keine** Keys in den Code – nur in Env‑Variablen.

---

## Grenzen (nochmal klar)

- Reine **Sprach**-Interaktion. Kein Bild, kein Video, kein Screen‑Mirroring.
- Antworten müssen in ~8s kommen, sonst bricht Alexa ab (lange JARVIS‑Tasks
  async beantworten lassen und eine kurze Bestätigung sprechen).
