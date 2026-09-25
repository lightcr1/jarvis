# Bereich: Voice / Audio

- Zweck: Sprachein-/ausgabe, Wakeword, TTS.
- Kern: `jarvis/api_voice.py`, `jarvis/audio_services.py`,
  `jarvis/wakeword_engine.py`, `jarvis/llm_utils.py`; Skripte
  `scripts/install_piper_voice.sh`.
- Konvention: Audio-Verarbeitung robust gegen fehlende Geräte/Modelle halten;
  externe Dienste hinter optionalen Providern kapseln.
- Tests: `tests/test_voice_api.py`, `tests/test_tts_preprocess.py`.
- Keine Cloud-/Bezahl-Dienste ohne explizite Freigabe.
