# Japanese / English wizard

Provide a persistent, visible language selector covering the five steps,
wardrobe editor, fitting/headgear controls, progress, errors and results.
Default to Japanese for Japanese browser languages, English otherwise.
Switch in place without resetting input, selected records, garment identities,
user names, source files, pending jobs or preview state. Language is a UI
preference, never a conversion setting or an instruction to translate a VRM.

Use Skyrim's own localized STRINGS/DLSTRINGS for record labels and descriptions,
including official equipment. English must request English tables explicitly;
never translate a Japanese Perk/spell/item name by machine or use Japanese as
an English fallback. If English data is missing, show the unchanged Editor ID
and explain the fallback. Keep IDs, plugin paths and FormIDs invariant.
Use canonical English skill, actor flag and AI-setting terminology.
Do not distribute extracted game string tables in the repository.

Static UI translations are explicit, reviewed resources. Dynamic messages
use parameterized translations; user/VRM text must never be processed as UI
translation keys. Preserve raw technical diagnostic details.

Verify through native language-table fixtures, actual installed English/Japanese
record readback and headless browser language controls. Exercise switch/reload,
all steps, category/search/selection, wardrobe, results, progress and failure,
including missing English tables and preservation of user-entered Japanese.

## Verification (2026-10-15)

- `python -m unittest discover -v`: 130 passed, including the native equipment,
  physics, seating and new localization regressions.
- `python -m ruff check --exclude dependencies,build,reference .`: passed.
- `python tests/browser-roles-fixture.py` reads installed masters and language
  tables into ignored local fixtures. `node tests/browser-localization.cjs`
  exercises English/Japanese controls, the five steps, native Stealth/Firebolt/
  Elven Helmet names, garment editing, a 390px viewport, exported IDs/settings,
  progress, failure, retry, completion and preference persistence.
- Existing Japanese role, original-headwear, saved-result and HTTP startup
  browser checks passed with an explicit Japanese browser locale.
- The installed English-named loose tables contained Japanese translations.
  The English archive fallback is verified against that actual condition;
  synthetic tests also cover absent English tables and language cache isolation.

User-entered Japanese names (including a name identical to a UI translation
key) remain unchanged. Language is not added to exported follower settings.
Game string fixtures and screenshots remain ignored local verification assets.
