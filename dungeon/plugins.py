import logging

from google.adk.models.google_llm import Gemini
from google.adk.plugins.base_plugin import BasePlugin

from . import config

log = logging.getLogger(__name__)


def is_quota_error(error):
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    text = str(error)
    return code == 429 or "RESOURCE_EXHAUSTED" in text or "429" in text[:40]


class GamePlugin(BasePlugin):
    """Two jobs.

    1. Remember the Session objects running invocations are using. A button
       press (attack, defend...) is written to the session service, and these
       in-memory copies are updated too, so a live connection that is already
       open sees the change on its next tool call.
    2. When a background model hits its quota, retry once on the fallback model.
    """

    def __init__(self):
        super().__init__(name="game")
        self.sessions = {}
        self.watched = set()

    async def before_run_callback(self, *, invocation_context):
        session = invocation_context.session
        if session.id in self.watched:
            seen = self.sessions.setdefault(session.id, [])
            if not any(s is session for s in seen):
                seen.append(session)
                del seen[:-3]
        return None

    async def on_model_error_callback(self, *, callback_context, llm_request, error):
        if not is_quota_error(error):
            return None
        fallback = config.FALLBACKS.get(llm_request.model)
        if not fallback:
            return None
        log.warning("quota hit on %s, retrying on %s", llm_request.model, fallback)
        llm_request.model = fallback
        last = None
        try:
            async for response in Gemini(model=fallback).generate_content_async(llm_request, stream=False):
                last = response
        except Exception as exc:  # the fallback is out of quota too
            log.warning("fallback %s failed: %s", fallback, exc)
            return None
        return last
