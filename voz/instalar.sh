#!/usr/bin/env bash
# Instala el motor de voz de SONQO (IndexTTS-2.5 con nuestra "config E") dentro de voz/.
# Es una instalación propia: no depende de ningún otro proyecto.
#
# Uso:  voz/instalar.sh                    # baja los pesos de Hugging Face (~7 GB)
#       PESOS=/ruta/checkpoints voz/instalar.sh   # o los copia de una carpeta local ya bajada
set -euo pipefail
cd "$(dirname "$0")"

CODIGO_COMMIT=$(sed -n 's/^base: //p' parches/BASE.txt)        # commit de index-tts que parcheamos
PESOS_REVISION=c39ce5ba981572cb187443877ff559dfb246ce63         # IndexTeam/IndexTTS-2.5 en Hugging Face

if [ ! -d index-tts ]; then
  git clone -q https://github.com/index-tts/index-tts.git index-tts
fi
git -C index-tts checkout -q "$CODIGO_COMMIT"
if git -C index-tts apply --check ../parches/index-tts.patch 2>/dev/null; then
  git -C index-tts apply ../parches/index-tts.patch
fi

if [ ! -f index-tts/checkpoints/gpt.pth ]; then
  if [ -n "${PESOS:-}" ]; then
    cp -r "$PESOS"/. index-tts/checkpoints/
  else
    uv tool install -q "huggingface-hub" || true
    hf download IndexTeam/IndexTTS-2.5 --revision "$PESOS_REVISION" --local-dir index-tts/checkpoints
  fi
fi

(cd index-tts && uv sync)
echo "Listo. Arranca la voz con: voz/arrancar.sh"
[ -f "$(dirname "$0")/voces/timbre_7s.wav" ] || echo "Falta la voz de referencia en voz/voces/timbre_7s.wav."
