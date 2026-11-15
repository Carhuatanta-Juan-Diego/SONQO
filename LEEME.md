# SONQO

**Monitoreo de salud sin contacto para astronautas lejos de la Tierra.**
NASA Space Apps Challenge 2026 · *Create Health Monitoring Software for Astronauts on Space Missions* · CsLabs, Chiclayo, Perú.

> Prototipo estudiantil. **No es un dispositivo médico.** Las reglas clínicas son ilustrativas. Toda fuente simulada lleva la etiqueta «simulado» en pantalla.

Desde Marte, un pedido de ayuda tarda de 3 a 22 minutos en llegar a la Tierra, y la respuesta lo mismo en volver. NASA-STD-3001 asigna a las misiones a Marte su nivel de atención médica más autónomo (Nivel V): la tripulación debe resolver a bordo. SONQO vigila a cada tripulante sin tocarlo, aprende su normal, le avisa cuando sale de él y qué hacer, y deja que **el astronauta decida**. A la Tierra solo viaja lo inesperado, en una tarjeta de 30 bytes.

English: [README.md](README.md).

## Qué hace

- **Mide sin contacto:** pulso con la cámara de color (algoritmo POS, Wang et al. 2017), respiración con radar y profundidad, temperatura de piel con cámara térmica. Una pulsera simple (pulso en la muñeca y vibración) lo acompaña entre módulos.
- **Aprende el normal de cada persona** (gemelo digital): una banda personal por indicador, un pronóstico de 60 s (filtro de Kalman) y un intervalo calibrado (predicción conformal). Nunca aprende de los desvíos, así que un episodio largo no se vuelve «normal».
- **Dos sensores deben coincidir** (dentro de 5 lpm) antes de alarmar. Si no coinciden, SONQO verifica primero y no alarma al astronauta.
- **Recomienda; el astronauta decide.** Motor de reglas con niveles de autonomía N0–N4. Nada de nivel N2 se ejecuta sin el «Sí» del astronauta en su pantalla **Mi estado**.
- **Tarjeta T-30:** toda una emergencia en 30 bytes con CRC, enviada en 4 copias por un enlace con retraso y decodificada campo por campo en la Tierra.
- **Caja negra:** cada lectura y decisión entra en una cadena de hash SHA-256. Cualquiera puede verificar que nada se editó y reproducir el registro para obtener la misma decisión.
- **Cascada de energía E0–E3:** en reposo solo vigila el radar (~2 W). Las cámaras térmica, de color y de profundidad despiertan solo para confirmar, y la cámara se libera de verdad cuando no hace falta.
- **SONQO, el asistente:** una esfera a la que se le habla o escribe. Responde con los datos en vivo del sistema («¿Cómo está MS-3?», «¿Llegó la alerta a la Tierra?», «Verifica la caja negra de MS-1»), avisa por su cuenta cuando alguien sale de su normal y se niega a autorizar nada en nombre del astronauta. Funciona con reglas, no es un modelo de lenguaje: no inventa y funciona sin internet. Habla con una voz neuronal local (opcional).

## Pantallas

Con el servidor corriendo: **http://localhost:8000** (inglés: `?lang=en`).

| Pantalla | Para quién | Qué muestra |
| --- | --- | --- |
| `/panel` | tripulación y equipo médico de a bordo | Inicio: una frase con lo importante ahora, la esfera de SONQO y las cuatro pulseras en vivo. Además ARCA, cajas negras, mediciones de rutina, enlace Tierra y datos NASA |
| `/estado?t=MS-3` | el tripulante | **Mi estado**: sus valores frente a su normal, la recomendación y «Sí, adelante» / «Ahora no» |
| `/tierra` | equipo médico en la Tierra | la tarjeta T-30 que llega con retraso, decodificada byte a byte |

La tripulación es MS-1 a MS-4. MS-2 tiene la cámara; MS-1, MS-3 y MS-4 corren la misma lógica con sensores simulados, cada uno con su gemelo, su Mi estado y su caja negra.

## Qué es real y qué es simulado

| Código real | Simulado en este sandbox |
| --- | --- |
| Algoritmo de pulso sin contacto (POS), fusión y regla de dos sensores, gemelo digital, motor de reglas, cascada de energía, codificador T-30 y canal con retraso, caja negra encadenada, asistente, interfaz | Radar, sensores térmico y de profundidad, la pulsera y la entrada de cámara (un video público de una cara en lugar de una webcam) |

Los umbrales clínicos son ilustrativos. El ARCA, una cápsula médica a bordo, es un concepto del equipo que se muestra solo como video generado con IA (con marca de agua).

## Correr

Requiere Python 3.11.

```bash
conda create -n sonqo python=3.11
conda activate sonqo
pip install -r requirements.txt
python -m sonqo.server --config config.yaml
```

**Entrada de cámara.** Sin webcam, SONQO lee un video de una cara por el mismo camino. Descarga `face.mp4` de la página *Eulerian Video Magnification* del MIT (https://people.csail.mit.edu/mrub/evm/) y guárdalo como `data/replay/cara.mp4`. No lo redistribuimos. Sin el video, pon `camara.fuente: replay` en `config.yaml`; con webcam, `camara.fuente: webcam`.

**Sandbox.** El botón «SANDBOX · simulador» abre el simulador: eliges un tripulante y un escenario (Reposo, Taquicardia, Sensor dañado). Cada tripulante primero aprende su normal unos 2 minutos (solo la primera vez; queda guardado en `data/perfiles/`).

**Voz neuronal (opcional).** La voz del asistente es IndexTTS-2.5 corriendo localmente en GPU (~4 GB de VRAM), como proceso aparte. Sin ella, SONQO usa la voz del navegador.

```bash
voz/instalar.sh     # una vez: clona index-tts, aplica voz/parches/ y baja los pesos (~16 GB)
voz/arrancar.sh     # en otra terminal; lista en ~40 s en http://127.0.0.1:8801
```

Las voces de referencia de `voz/voces/` están grabadas con consentimiento. IndexTTS está bajo la bilibili Model Use License.

## Pruebas y caja negra

```bash
pytest -q                                                        # 53 pruebas
python -m sonqo.blackbox verificar  data/caja_negra/<archivo>.jsonl  # ¿se editó algo?
python -m sonqo.blackbox reproducir data/caja_negra/<archivo>.jsonl  # ¿misma decisión al reproducir?
```

El codificador T-30 reproduce byte a byte el vector de prueba (`tests/test_t30.py`).

## Repositorio

```
sonqo/          servidor (FastAPI + WebSocket), sensores, fusión, gemelo, reglas, energía, T-30, caja negra
web/            interfaz: JavaScript y canvas/WebGL, sin CDNs, funciona sin internet
voz/            servidor opcional de voz neuronal local
tests/          pruebas con pytest
scripts/        generador de reproducciones y reporte de error cámara vs oxímetro
data/replay/    series de reproducción de respiración y del caso simulado
config.yaml     fuentes, tripulación, energía, voz
```

## Recursos de NASA

SONQO usa recursos de NASA para fijar sus requisitos y parámetros. El prototipo todavía no procesa una serie de datos de NASA: sus señales son simuladas. La sección **Datos NASA** del software muestra esta misma tabla.

| Fuente | Qué fija en SONQO |
| --- | --- |
| [NASA-STD-3001, Vol. 1 (Crew Health)](https://ntrs.nasa.gov/api/citations/20170000500/downloads/20170000500.pdf) | Marte es atención de Nivel V: SONQO decide a bordo y el astronauta tiene la última palabra |
| [NASA Integrated Medical Model (IMM)](https://www.nasa.gov/nasa-integrated-medical-model-imm-overview/) | ~100 condiciones médicas posibles; respalda los niveles de autonomía N0–N4 |
| [ASCEND: retrasos de comunicación en misiones tripuladas a Marte](https://ntrs.nasa.gov/api/citations/20220013418/downloads/ASCEND-Communication%20Delays%2C%20Disruptions%2C%20and%20Blackouts%20for%20Crewed%20Mars%20Missions.pdf) y DSOC (NASA/JPL) | 3–22 min de ida, hasta ~44 min ida y vuelta, apagones en la conjunción solar: 30 bytes, 4 copias, entrega con retraso, sin esperar a la Tierra |
| [Detector RAD de Curiosity](https://www.swri.org/newsroom/press-releases/swri-led-team-calculates-the-radiation-exposure-associated-trip-mars) | 1,84 mSv/día en tránsito: el campo de dosis de radiación de la T-30 |
| [NASA OSDR · estudios abiertos de Inspiration4](https://www.nasa.gov/osdr-latest-news-i4-mission-datasets/) | qué guarda la caja negra para que sirva a la investigación; siguiente paso: reproducir datos reales de tripulantes |
| [NASA HRP: distancia a la Tierra](https://www.nasa.gov/hrp/hazard-distance-from-earth/) | pérdida ósea y SANS: los siguientes indicadores del gemelo |

También: el Bio-Monitor (Astroskin) de la Agencia Espacial Canadiense como precedente de la pulsera, y el procesamiento a bordo de datos de wearables en la misión Axiom 4 del ISS National Lab.

## Referencias

- Wang, W., den Brinker, A. C., Stuijk, S., de Haan, G. (2017). *Algorithmic Principles of Remote PPG*. IEEE TBME.
- Wu, H.-Y. et al. (2012). *Eulerian Video Magnification*. SIGGRAPH, MIT CSAIL (video de cara usado como entrada de cámara; no se redistribuye).
- Google MediaPipe Face Mesh (Apache 2.0), OpenCV, NumPy, SciPy, FastAPI, Uvicorn, PyYAML, pytest, IndexTTS.
- No se usa el logo de NASA, según las reglas de Space Apps.
