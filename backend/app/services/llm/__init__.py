"""LLM client services — transversal provider abstraction for the agent pipeline.

For s02 only ``minimax`` (routed via OpenRouter) and ``openai`` are wired
through ``ChatOpenAI``. ``ollama`` is intentionally not supported — see
``build_llm_client`` and the s02 plan § "Run interdicts".
"""
