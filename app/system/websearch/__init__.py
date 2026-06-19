"""Websearch provider layer.

Borb's dedicated web search capability. Mirrors the LLM provider layer
(:mod:`app.llm`): a thin provider interface (:class:`WebsearchProviderBase`)
with concrete backends and a router that selects one from configuration.
"""
