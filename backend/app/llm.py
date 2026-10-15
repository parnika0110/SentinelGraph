"""Optional LLM provider abstraction.

The investigation pipeline NEVER depends on an LLM: all graph retrieval,
correlation, ranking and evidence assembly happen in pure Python/Cypher.
When configured, an LLM may only *summarize already-retrieved evidence*.

Providers:
  * "openai"  -> OpenAI-compatible chat completions (needs llm_api_key)
  * anything else / empty -> deterministic local summarizer (no key required)

Guardrails enforced here:
  * The prompt contains ONLY retrieved evidence strings passed by the engine.
  * The prompt instructs the model not to add facts beyond the evidence.
  * If any provider call fails, we fall back to the local summarizer.
"""

from __future__ import annotations

from app.config import Settings, get_settings


def _local_summary(title: str, evidence_lines: list[str], hypotheses: list[str]) -> str:
    """Deterministic, evidence-only summary (no API key required)."""
    lines = [f"{title}", ""]
    lines.append("Graph-retrieved evidence:")
    for i, e in enumerate(evidence_lines[:8], start=1):
        lines.append(f"  {i}. {e}")
    if hypotheses:
        lines.append("")
        lines.append("Working hypotheses:")
        for h in hypotheses[:5]:
            lines.append(f"  - {h}")
    lines.append("")
    lines.append(
        "Summary generated locally from FalkorDB results only; no external model "
        "was used."
    )
    return "\n".join(lines)


def _openai_summary(
    title: str, evidence_lines: list[str], hypotheses: list[str], settings: Settings
) -> str:
    import httpx

    system = (
        "You are a SOC analyst writing an incident brief. Use ONLY the evidence "
        "provided. Do not invent facts, entities, timestamps or relationships. "
        "Clearly separate observed facts from hypotheses. Keep it under 200 words."
    )
    user = (
        f"Incident: {title}\n\nEvidence retrieved from the graph database:\n"
        + "\n".join(f"- {e}" for e in evidence_lines)
        + "\n\nHypotheses:\n"
        + "\n".join(f"- {h}" for h in hypotheses)
    )
    base = settings.llm_provider.rstrip("/")
    url = base if base.endswith("/chat/completions") else base + "/chat/completions"
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def summarize(
    title: str,
    evidence_lines: list[str],
    hypotheses: list[str],
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Return (summary_text, provider_name).

    Never raises: falls back to the local summarizer on any failure.
    """
    settings = settings or get_settings()
    provider = (settings.llm_provider or "").strip().lower()

    if provider == "openai" and settings.llm_api_key:
        try:
            return _openai_summary(title, evidence_lines, hypotheses, settings), "openai"
        except Exception:
            # Fall back silently; the pipeline must work without the LLM.
            return (
                _local_summary(title, evidence_lines, hypotheses) + "\n\n"
                "(LLM summarizer unavailable; local evidence-only summary used.)",
                "local-fallback",
            )

    return _local_summary(title, evidence_lines, hypotheses), "local"
