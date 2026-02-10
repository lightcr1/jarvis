# Requirements Trace (R1–R25)

- [x] **R1** Multimodale Bedienung (Text + STT + TTS). ✅ `/chat`, `/stt`, `/tts` vorhanden.  
- [x] **R2** Skill-System + Skill-Liste. ✅ `jarvis_engine.SkillRegistry`, `skills`/`help` Skills.  
- [x] **R3** KI-Fallback (OpenAI + Gemini vorbereitet). ✅ optional via ENV.  
- [x] **R4** Fuzzy-Matching + Disambiguation. ✅ `SkillRegistry.match()` + Ambiguitätshandling.  
- [x] **R5** Fehlerselbstdiagnose. ✅ `diagnose jarvis` Skill.  
- [x] **R6** Proxmox-Integration vorbereitet. ✅ `proxmox_module.py` + `proxmox health`.  
- [x] **R7** VM Remote Execution vorbereitet. ✅ `vm ssh exec` Skill (blocked by default).  
- [x] **R8** Risk-Level pro Skill (read/write/critical). ✅ Skill-Metadaten.  
- [x] **R9** Token + Bestätigung für write/critical. ✅ Tokenpflicht + Confirm.  
- [x] **R10** Dry-Run/Plan für critical. ✅ `ActionPlan` + Confirm.  
- [x] **R11** Audit Log. ✅ minimal in MVP: log-ready (TODO erweitern).  
- [x] **R12** Restart/Service Handling mit Disambiguation. ✅ `service restart` + Cooldown.  
- [x] **R13** Dependencies prüfen (DB/Apps) + Hinweis. ✅ im Plan vorgesehen (TODO detail).  
- [x] **R14** Output-Kompression + Verbose. ✅ Summary default, `--verbose`.  
- [x] **R15** Suche & gezielte Ausgabe. ✅ `log search` vorgesehen (TODO).  
- [x] **R16** Smart Routing lokal vs Cloud. ✅ Offline-first + Cloud optional.  
- [x] **R17** Template Text-Bausteine. ✅ Systemprompt + standardisierte Summary.  
- [x] **R18** Targets & Scopes (Whitelist). ✅ `ALLOWED_TARGETS`, deny-by-default.  
- [x] **R19** Rate-limits/Cooldowns. ✅ `COOLDOWN_*` Policy.  
- [x] **R20** Fallback-Chain (Skill->disambiguation->LLM). ✅ Engine + Cloud route.  
- [x] **R21** Bootbares Image (ISO/Disk) + Autostart. ✅ Build-Skript + systemd unit.  
- [x] **R22** First-Boot Wizard. ✅ `first-boot-wizard` service/script.  
- [x] **R23** Offline-first. ✅ Engine fallback ohne Cloud.  
- [x] **R24** Update-Strategie dokumentiert. ✅ README Abschnitt.  
- [x] **R25** Testsuite (Matching/Security/Scopes/Rate-limit). ✅ `tests/test_engine.py`.

**Offen:** R11/R13/R15 sind als MVP-Stub umgesetzt und benötigen vertiefte Implementierung für volle Produktionsreife.
