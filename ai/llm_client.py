"""
LLM client — thin wrapper over litellm with retry logic.
Supports any OpenAI-compatible model/proxy via env vars.
"""
import litellm
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.config import get_settings

log = structlog.get_logger()

# litellm config
litellm.drop_params = True  # silently drop unsupported params per model


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((litellm.APIConnectionError, litellm.Timeout)),
)
async def call_llm(
    system: str,
    user: str,
    response_format: str = "text",   # "text" or "json"
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> str:
    """
    Call the configured LLM and return the response text.

    Args:
        system:          System prompt
        user:            User message
        response_format: "text" or "json" (enables JSON mode when supported)
        temperature:     Sampling temperature (lower = more deterministic)
        max_tokens:      Max output tokens

    Returns:
        Response content as a string.
    """
    settings = get_settings()

    kwargs = dict(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=settings.openai_api_key or None,
    )

    if settings.openai_api_base:
        kwargs["api_base"] = settings.openai_api_base

    if response_format == "json":
        kwargs["response_format"] = {"type": "json_object"}

    log.debug("llm.call", model=settings.llm_model, prompt_chars=len(user))
    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content or ""
    log.debug("llm.response", chars=len(content))
    return content
