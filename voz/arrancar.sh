#!/usr/bin/env bash
# Arranca la voz de SONQO (IndexTTS-2.5) en http://127.0.0.1:8801.
# Tarda ~30-60 s en cargar el modelo. Dejarlo corriendo en otra terminal junto a SONQO.
# Necesita la GPU libre (~4 GB): un solo proceso de voz a la vez (revisar con nvidia-smi).
set -euo pipefail
cd "$(dirname "$0")"
# sin internet: los pesos ya están aquí; una red de la sede que cuelga no debe colgar el arranque
export HF_HUB_OFFLINE=1
exec uv run --directory index-tts --no-sync python ../servidor_voz.py --http "${PUERTO:-8801}" --sin-consola "$@"
