# Backend provenance

Imported from https://github.com/prathiksh13/fac_rag

Pinned commit: `6ba86142c78f85ff48453bb3645040f6392b376e`

The Python source, tests, configuration template, original README and data-folder placeholders are copied byte-for-byte. No retrieval, discovery, ranking, generation, scoring, consent or verification implementation was changed.

The upstream `demo-web/` folder is preserved separately at `examples/upstream-demo-web/`. It is an upstream example, not the ResearchMate website. This placement also respects ResearchMate's existing TypeScript exclusion of `examples/`.

`UPSTREAM_MANIFEST.json` maps every original tracked path to its new location and records its upstream Git blob SHA. Added ResearchMate integration files live outside this imported source.

The uploaded private environment configuration is used locally as `backend/.env`; it is not committed. The repository's safe `.env.example` is retained. Upstream `pyproject.toml` declares the project license as MIT; no new license text has been attributed to the upstream author.
