#!/usr/bin/env bash
#
# Ein-Befehl-Deploy des Alexa -> JARVIS Skills als Alexa-hosted Skill.
# (Alexa-hosted = Amazon stellt die Lambda kostenlos bereit, du brauchst KEIN AWS-Konto.)
#
# Voraussetzungen (einmalig):
#   - Node.js installiert
#   - ASK CLI:  npm install -g ask-cli
#
# Dann einfach:
#   ./deploy.sh
#
# Beim ersten Mal öffnet sich der Browser für den Amazon-Login (DEIN Konto, auf dem
# auch dein Echo registriert ist). Das ist der einzige manuelle Schritt und kann
# niemandem abgenommen werden, weil der Skill in dein Konto deployt wird.

set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ask >/dev/null 2>&1; then
  echo "FEHLER: ASK CLI nicht gefunden."
  echo "Installieren mit:  npm install -g ask-cli"
  exit 1
fi

# Einmaliger Login, falls noch nicht konfiguriert.
if [ ! -f "$HOME/.ask/cli_config" ]; then
  echo ">> Einmaliger Amazon-Login (Browser öffnet sich) ..."
  ask configure
fi

echo ">> Deploye Skill (Interaction Model + Backend) ..."
ask deploy

cat <<'DONE'

Fertig.
- Der Skill liegt jetzt auf deinem Amazon-Konto und ist auf deinem Echo (Spot) nutzbar:
    "Alexa, öffne mein jarvis"  ->  dann z.B. "frag nach dem wetter"
- Er funktioniert sofort, auch ohne JARVIS (er bestaetigt, was er verstanden hat).
- Sobald JARVIS laeuft: JARVIS_ENDPOINT als Umgebungsvariable des Skills setzen
  (Alexa Developer Console -> Code -> Environment, oder per 'ask' SMAPI),
  dann leitet der Skill alles an JARVIS weiter.
DONE
