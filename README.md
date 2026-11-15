# SONQO

**Contactless health monitoring for astronauts far from Earth.**
NASA Space Apps Challenge 2026 · *Create Health Monitoring Software for Astronauts on Space Missions* · Team CsLabs, Chiclayo, Peru.

> Student prototype. **Not a medical device.** Clinical rules are illustrative. Every simulated source is labeled "simulated" on screen.

From Mars, a call for help takes 3 to 22 minutes to reach Earth, and the answer just as long to come back. NASA-STD-3001 puts Mars missions at its most autonomous level of medical care (Level V): the crew must handle problems on board. SONQO watches each crew member without touching them, learns their personal normal, tells them when they leave it and what to do, and lets **the astronaut decide**. Only the unexpected travels to Earth, in a 30-byte card.

Documentación en español: [LEEME.md](LEEME.md).

## What it does

- **Measures without contact:** pulse from the color camera (POS algorithm, Wang et al. 2017), breathing from radar and depth, skin temperature from a thermal camera. A simple wristband (wrist pulse and vibration) follows the astronaut between modules.
- **Learns each person's normal** (a digital twin): a personal band per indicator, a 60 s forecast (Kalman filter) and a calibrated interval (conformal prediction). It never learns from deviations, so a long episode never becomes "normal".
- **Two sensors must agree** (within 5 bpm) before any alarm. If they disagree, SONQO checks first and does not alarm the astronaut.
- **Recommends; the astronaut decides.** A rules engine with autonomy levels N0–N4. Nothing at level N2 runs without the astronaut's "Yes" on their own **My status** screen.
- **T-30 card:** a whole emergency in 30 bytes with a CRC, sent in 4 copies over a delayed link and decoded field by field on Earth.
- **Black box:** every reading and decision goes into a SHA-256 hash chain. Anyone can verify that nothing was edited and replay the log to get the same decision.
- **Energy cascade E0–E3:** at rest only the radar watches (~2 W). Thermal, color and depth cameras wake up only to confirm, and the camera is truly released when not needed.
- **SONQO, the assistant:** a sphere you can talk or type to. It answers from the system's live data ("How is MS-3?", "Did the alert reach Earth?", "Verify MS-1's black box"), warns by itself when someone leaves their normal and refuses to authorize anything on the astronaut's behalf. It is rule-based, not a language model: it does not make things up and it works offline. It speaks with a local neural voice (optional).

## Screens

Run the server and open **http://localhost:8000** (English: `?lang=en`).

| Screen | For whom | What it shows |
| --- | --- | --- |
| `/panel` | crew and on-board medical team | Home: one sentence with what matters now, the SONQO sphere and the four crew wristbands live. Plus ARCA, black boxes, routine measurements, Earth link and NASA data |
| `/estado?t=MS-3` | the crew member | **My status**: their values against their own normal, the recommendation and "Yes, go ahead" / "Not now" |
| `/tierra` | medical team on Earth | the T-30 card arriving with delay, decoded byte by byte |

The crew is MS-1 to MS-4. MS-2 has the camera; MS-1, MS-3 and MS-4 run the same logic on simulated sensors, each with its own twin, its own My status and its own black box.

## What is real and what is simulated

| Real code | Simulated in this sandbox |
| --- | --- |
| Contactless pulse algorithm (POS), fusion and two-sensor rule, digital twin, rules engine, energy cascade, T-30 encoder and delayed channel, hash-chained black box, assistant, interface | Radar, thermal and depth sensors, the wristband, and the camera input (a public face video instead of a webcam) |

Clinical thresholds are illustrative. ARCA, an on-board medical capsule, is a team concept shown only as an AI-generated video (watermarked).

## Run it

Requires Python 3.11.

```bash
conda create -n sonqo python=3.11
conda activate sonqo
pip install -r requirements.txt
python -m sonqo.server --config config.yaml
```

**Camera input.** Without a webcam, SONQO reads a face video through the same pipeline. Download `face.mp4` from MIT's *Eulerian Video Magnification* page (https://people.csail.mit.edu/mrub/evm/) and save it as `data/replay/cara.mp4`. We do not redistribute it. Without the video, set `camara.fuente: replay` in `config.yaml`; with a webcam, `camara.fuente: webcam`.

**Sandbox.** The "SANDBOX · simulator" button opens the simulator: pick a crew member and a scenario (Rest, Tachycardia, Damaged sensor). Each crew member first learns their normal for about 2 minutes (only the first time; it is saved in `data/perfiles/`).

**Neural voice (optional).** The assistant's voice is IndexTTS-2.5 running locally on a GPU (~4 GB VRAM), as a separate process. Without it, SONQO uses the browser's voice.

```bash
voz/instalar.sh     # once: clones index-tts, applies voz/parches/ and downloads the weights (~16 GB)
voz/arrancar.sh     # in another terminal; ready in ~40 s at http://127.0.0.1:8801
```

The reference voices in `voz/voces/` are recorded with consent. IndexTTS is under the bilibili Model Use License.

## Tests and black box

```bash
pytest -q                                                      # 53 tests
python -m sonqo.blackbox verificar  data/caja_negra/<file>.jsonl  # was anything edited?
python -m sonqo.blackbox reproducir data/caja_negra/<file>.jsonl  # same decision on replay?
```

The T-30 encoder reproduces the test vector byte for byte (`tests/test_t30.py`).

## Repository

```
sonqo/          server (FastAPI + WebSocket), sensors, fusion, twin, rules, energy, T-30, black box
web/            interface: plain JavaScript and canvas/WebGL, no CDNs, works offline
voz/            optional local neural voice server
tests/          pytest suite
scripts/        replay generator and camera-vs-oximeter error report
data/replay/    replay series for breathing and the simulated case
config.yaml     sources, crew, energy, voice
```

## NASA resources

SONQO uses NASA resources to set its requirements and parameters. The prototype does not yet process a NASA data series: its signals are simulated. The **NASA data** section of the software shows this same table.

| Source | What it sets in SONQO |
| --- | --- |
| [NASA-STD-3001, Vol. 1 (Crew Health)](https://ntrs.nasa.gov/api/citations/20170000500/downloads/20170000500.pdf) | Mars missions are Level V care: SONQO decides on board and the astronaut has the final say |
| [NASA Integrated Medical Model (IMM)](https://www.nasa.gov/nasa-integrated-medical-model-imm-overview/) | ~100 possible medical conditions; supports the N0–N4 autonomy levels |
| [ASCEND: Communication delays for crewed Mars missions](https://ntrs.nasa.gov/api/citations/20220013418/downloads/ASCEND-Communication%20Delays%2C%20Disruptions%2C%20and%20Blackouts%20for%20Crewed%20Mars%20Missions.pdf) and DSOC (NASA/JPL) | 3–22 min one way, up to ~44 min round trip, blackouts at solar conjunction: 30 bytes, 4 copies, delayed delivery, no waiting for Earth |
| [Curiosity RAD detector](https://www.swri.org/newsroom/press-releases/swri-led-team-calculates-the-radiation-exposure-associated-trip-mars) | 1.84 mSv/day in transit: the radiation dose field of the T-30 card |
| [NASA OSDR · Inspiration4 open studies](https://www.nasa.gov/osdr-latest-news-i4-mission-datasets/) | what the black box keeps so it is useful for research; next step: replay real crew data |
| [NASA HRP: distance from Earth](https://www.nasa.gov/hrp/hazard-distance-from-earth/) | bone loss and SANS: the next indicators for the twin |

Also: the Canadian Space Agency's Bio-Monitor (Astroskin) as precedent for the wearable add-on, and the ISS National Lab Axiom Mission 4 on-board processing of wearable data.

## References

- Wang, W., den Brinker, A. C., Stuijk, S., de Haan, G. (2017). *Algorithmic Principles of Remote PPG*. IEEE TBME.
- Wu, H.-Y. et al. (2012). *Eulerian Video Magnification*. SIGGRAPH, MIT CSAIL (face video used as camera input; not redistributed).
- Google MediaPipe Face Mesh (Apache 2.0), OpenCV, NumPy, SciPy, FastAPI, Uvicorn, PyYAML, pytest, IndexTTS.
- No NASA logos are used, per Space Apps rules.
