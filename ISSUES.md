# Deferred catalog work

- **Release blocker:** give the NAS runner a reliable route to the OpenFreeMap Cloudflare bucket, preferably through an existing VPN or trusted proxy. Direct NAS requests receive only about 20 KiB before stalling. A split-range proxy successfully extracted and verified a 9.9 MiB Yerevan pack in 14.6 seconds (`34480674217`), but the 202 MiB Moscow Oblast transfer eventually exhausted retries after creating tens of thousands of 4 KiB upstream requests (`34482314250`). This workaround is retained as a diagnostic, not used by the weekly workflow. Keep the weekly cron disabled until a normal large-range smoke test and a representative regional build both succeed over the new route.

- Replace older pinned Kazakhstan and other stale ADM1 geometries when a suitable current, openly redistributable and internally consistent source is selected.
- Add a separately validated Ashgabat boundary; the pinned Turkmenistan ADM1 file contains five velayats although its upstream metadata reports six units.
- Decide whether Moldova's 37 and Azerbaijan's 79 small packs should remain separate or become larger product regions.
- Add controlled border overlap if field testing shows gaps when only one adjacent regional pack is installed.
- Integrate local PMTiles reading and offline fonts, sprites and Natural Earth assets into ANAV.
