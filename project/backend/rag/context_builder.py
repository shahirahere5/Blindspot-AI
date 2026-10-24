"""
Converts retrieved chunks into grounded, source-labeled context text for the
AI -- the last step before a prompt is built (see ai/prompts.py and
ai/debate_prompts.py, which are otherwise unchanged by Phase 4).

Every location in the returned text, and in the returned `valid_locations`
set, comes directly from a `DocumentChunk.source_location` that was itself
copied from a real `ContentBlock` (see rag/chunking.py) -- nothing here can
invent a page/slide number.
"""

from __future__ import annotations

from schemas.rag import RetrievedChunk


def build_rag_context(retrieved_chunks: list[RetrievedChunk]) -> tuple[str, set[int]]:
    """
    Render retrieved chunks as labeled context text, e.g.:

        [Source: Page 2]
        <chunk text>

        [Source: Slide 5]
        <chunk text>

    Returns (context_text, valid_locations) where valid_locations is the
    set of source locations actually present in the retrieved chunks --
    i.e. exactly what the model was shown, which is what its
    `source_locations` citations should be validated against (see
    services/rag_service.py).
    """
    sections: list[str] = []
    valid_locations: set[int] = set()

    for retrieved in retrieved_chunks:
        chunk = retrieved.chunk
        label = chunk.source_type.capitalize()
        sections.append(f"[Source: {label} {chunk.source_location}]\n{chunk.text}")
        valid_locations.add(chunk.source_location)

    return "\n\n".join(sections), valid_locations
