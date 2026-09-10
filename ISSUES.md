# Deferred catalog work

- **Release blocker:** choose a production tile schema and source path that supports planet-scale PMTiles range extraction from GitHub-hosted runners. OpenFreeMap run `34455972382` lost its runner after 52 minutes while extracting the 8.3 MB Yerevan pack; the same command completed locally in 18 seconds. Protomaps probe `34469152600` extracted and verified the same 138 tiles in 6.16 seconds, but uses a different basemap layer schema. Keep the weekly cron disabled until that compatibility decision is made and the production smoke workflow succeeds.

- Replace older pinned Kazakhstan and other stale ADM1 geometries when a suitable current, openly redistributable and internally consistent source is selected.
- Add a separately validated Ashgabat boundary; the pinned Turkmenistan ADM1 file contains five velayats although its upstream metadata reports six units.
- Decide whether Moldova's 37 and Azerbaijan's 79 small packs should remain separate or become larger product regions.
- Add controlled border overlap if field testing shows gaps when only one adjacent regional pack is installed.
- Integrate local PMTiles reading and offline fonts, sprites and Natural Earth assets into ANAV.
