"""System-prompt guidance per model profile.

The transport (base_url/model/api_key) lives in config profiles; this adds the
task framing. The house no-em-dash rule is enforced here for any profile that
generates prose that lands in the wiki.
"""

from __future__ import annotations

NO_EM_DASH_RULE = (
    "Never use em dashes. Use commas, parentheses, colons, or separate sentences instead."
)

WIKI_AUTHOR_SYSTEM = (
    "You maintain a persistent, interlinked wiki over Norwegian DISKOS petroleum "
    "borehole data (palynology, well logs, XRF). Write concise, factual markdown. "
    "Cross-reference related wells, species, and formations with [[wikilinks]]. "
    "State uncertainty plainly and flag where new data contradicts existing pages. "
    + NO_EM_DASH_RULE
)

JACK_SERVE_SYSTEM = (
    "You answer questions about DISKOS borehole data for a working geologist. Be "
    "direct and quantitative. Cite the wells and depths you draw from. " + NO_EM_DASH_RULE
)

_SYSTEM_PROMPTS = {
    "wiki-author": WIKI_AUTHOR_SYSTEM,
    "jack-serve": JACK_SERVE_SYSTEM,
}


def system_prompt_for(profile_name: str) -> str:
    """Return the system prompt for a profile (empty string if none defined)."""
    return _SYSTEM_PROMPTS.get(profile_name, "")
