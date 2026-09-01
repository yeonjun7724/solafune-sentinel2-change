# vendor/

Empty in the source tree. `scripts/build_qgis_plugin.py` copies
`src/solafune_change/` into `vendor/solafune_change/` when it builds the
release ZIP, so the shipped plugin carries a working copy of the core engine
without a second, hand-maintained copy of the source ever existing in this
repository. `core_bridge.py` looks here only after an already-installed
`solafune_change` fails to import.

Do not hand-edit anything under `vendor/` — it is a build artifact and is
regenerated (deleted and recopied) on every build.
