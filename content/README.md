# Dark Eden content sources

Treasure JSON in `src/treasure/` is the editable development source. The files
under `reference/treasure/` are the untouched original binary fixtures. Do not
edit the fixtures to make a change pass verification; they are retained for
regression comparison and recovery.

The Python toolkit is build-time only. It writes legacy `.bin` files into a
staging directory. The gameserver continues to read its existing binary format
and does not need Python or JSON support.

## Layout

- `src/treasure/<resource stem>.json`: authoritative editable table.
- `schema/treasure.schema.json`: version 1 JSON Schema.
- `catalogs/treasure-reference-ids.json`: item and option IDs and English labels
  extracted from the checked-in `DARKEDEN.sql` seed; used to catch unknown
  class, item-type, and option references.
- `reference/treasure/<original filename>.bin`: original regression fixtures.
- `../content_tools/`: reusable Python 3 codec, validator, and command line.

Each JSON file records its exact legacy output name in `source_file`. Arrays
are ordered and compiled without sorting or weight normalization. Optional
`label` properties can be added to an item class, item type, or option for
editor readability; labels are ignored by the binary compiler.

## Check and build content only

From the repository root, with Python 3.10 or newer:

```bash
python3 -m unittest discover -s content_tools/tests -v
python3 -m content_tools verify
python3 -m content_tools compile --output build/content/data
```

`verify` requires every source to compile to the exact bytes in its original
fixture. It is expected to fail after an intentional loot edit. For edited
content, run the unit tests and `compile`; the compiler validates all source
records and reference IDs, then writes only generated treasure binaries plus a
build provenance file under `build/content/data/`.

The checked-in reference catalog reflects the checked-in database seed, not a
custom live database. When adding items to a custom database, export its
`DARKEDEN` schema/data as a private SQL dump and regenerate the catalog from
that dump. The catalog itself contains only item/option IDs and English display
labels; do not commit a private dump. The catalog generator verifies every
table mapping used by treasure classes.

## Modify a loot table

1. Copy the relevant JSON file as a backup or use version control.
2. Edit the ordered records in `src/treasure/`. Adjust integer values directly;
   do not convert weights to percentages or normalize them. For example,
   `Class1.slayer.json` compiles back to `Class1.slayer.bin`.
3. Keep `source_file` unchanged unless deliberately renaming the runtime
   resource. Keep class, item-type, and option IDs valid in the reference
   catalog (or update that catalog from the matching database).
4. Run the unit tests, then compile to a staging path:

   ```bash
   python3 -m unittest discover -s content_tools/tests -v
   python3 -m content_tools compile --output build/content/data
   ```

If the table uses a valid item or option newly added to the matching database,
refresh the catalog before compiling:

```bash
python3 -m content_tools catalog-from-sql --sql /path/to/private-DARKEDEN.sql \
  --output content/catalogs/treasure-reference-ids.json
```

Review the catalog diff and commit it with the loot change. Use the same seed or
dump version as the server being built.

The compile command does not touch `data/` or the reference fixtures. Review
the JSON diff, generated binary diff, and catalog changes before packaging.

## Docker build and cache behavior

The selfbuilt image has an independent `content-builder` stage. It copies only
the toolkit, JSON, schema, and reference catalog, validates and compiles them,
then the runtime stage overlays those generated treasure files on the original
`data/` directory. Other resources are copied from `data/` unchanged. The
content stage never supplies input to the C++ compilation stage, so changing
treasure JSON rebuilds content and the final image while Docker can reuse the
cached loginserver/sharedserver/gameserver build layers.

Build the test deployment with the existing Compose file:

```bash
docker compose -f standalone/compose.selfbuilt.yaml build game
docker compose -f standalone/compose.selfbuilt.yaml up -d
docker compose -f standalone/compose.selfbuilt.yaml logs --tail=200 game
```

For ordinary Docker, build the same image directly from the repository root:

```bash
docker build -f Dockerfile.selfbuilt -t darkeden-selfbuilt:local .
```

No gameplay loader or runtime parser changes are part of this pipeline.
