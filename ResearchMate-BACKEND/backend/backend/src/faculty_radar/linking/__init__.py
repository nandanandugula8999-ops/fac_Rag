"""Faculty and publication linking.

Stage 4 of the pipeline. Attaches publications to canonical faculty profiles.

Responsibilities:
  * link faculty profiles to the resolved researcher identities they own
  * attach publication metadata: title, abstract, venue, year, DOI, open-access
    URL, citation count
  * filter to consented, in-scope faculty only
  * preserve an explicit `link_confidence` and `link_method` per edge

Output feeds the knowledge graph, the chunk corpus, and the evidence trails
that make a ranking defensible.

Consent is enforced here as a data gate, not as a flag that downstream code
remembers to check: a researcher with no entry in the consent registry produces
no `FacultyProfile` at all, so an unconsented person cannot reach retrieval,
ranking, or the LLM. See `linking.consent`.

Submodules:
  consent  - the opt-in registry that gates discoverability
  builder  - researchers + works -> FacultyProfile with linked publications
  store    - persistence under `paths.processed`
"""

from faculty_radar.linking.builder import FacultyLinker, link_faculty
from faculty_radar.linking.consent import ConsentRegistry, load_consent_registry
from faculty_radar.linking.store import FacultyStore

__all__ = [
    "ConsentRegistry",
    "FacultyLinker",
    "FacultyStore",
    "link_faculty",
    "load_consent_registry",
]
