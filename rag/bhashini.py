"""Bhashini (ULCA / Dhruva) translation client.

Bhashini is the Government of India's national language-technology mission and
the national language infrastructure a multilingual Indian assistant should
speak to. Everything else in this system runs on the machine in front of you; this
module is the one deliberate exception, and the whole file is written around
that fact.

WHY IT IS HERE
--------------
The local translation path works but is the weakest link in the stack. Measured
on this machine, qwen2.5:1.5b renders the Tamil for "can I get a patent for
Giloy?" as "What is the medicinal use of Giloy (Licorice)?" -- wrong intent,
wrong plant, no warning. Writing *into* an Indic language is worse: the small
models loop, or silently translate "Section 21", which the terminology lock
forbids. Bhashini's IndicTrans2 models are trained for exactly these pairs and
do not have those failure modes.

WHAT IT COSTS, STATED PLAINLY
-----------------------------
Calling Bhashini sends the text to a remote service. That is a real change from
"nothing leaves this machine", so:

  * It is OFF unless credentials are configured. No credentials, no call, no
    prompt, no degradation -- the local path is unchanged.
  * AYURLEX_BHASHINI=0 turns it off even when credentials are present.
  * Nothing is written to disk here, in or out. The no-disk rule is untouched:
    sessions stay in-process and ephemeral.
  * `status()` reports whether it is on, and the health endpoint serves that,
    so a user is never translated remotely without being able to see it.

The compile and classification paths do not call this module, and must not.
They are deterministic and local by design, and that is the demo's strongest
claim.

WHAT IT DOES NOT CHANGE
-----------------------
Not one of the output guards is relaxed for Bhashini. A translated answer still
has to be in the right script, non-degenerate, and still has to carry every
section number, Act name and citation marker verbatim, or it is discarded and
the English is returned. Bhashini is a better translator, not a trusted one:
`protect`/`restore` below mask the immutable tokens before the text is sent so
that the invariant holds by construction, and the guards in rag/translate.py
still run afterwards to catch the case where the service drops a mask.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# The MeitY-hosted pipeline. Overridable, because an organisation running its
# own ULCA deployment will have a different pipeline id and endpoint.
AUTH_URL = os.environ.get(
    "BHASHINI_AUTH_URL",
    "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline",
)
DEFAULT_PIPELINE = "64392f96daac500b55c543cd"

# Bhashini speaks ISO 639-1 for the languages core/language.py detects, so the
# codes pass straight through. Listed explicitly rather than assumed: sending a
# code the service does not serve returns a 200 with an empty target, which
# looks exactly like a good translation of an empty string.
SUPPORTED = {
    "hi", "ta", "te", "kn", "ml", "bn", "gu", "pa", "or", "ur", "as", "mr",
    "ne", "sa", "sd", "si", "mai", "brx", "mni", "doi", "kok", "ks", "sat",
    "en",
}


class BhashiniUnavailable(RuntimeError):
    pass


@dataclass
class BhashiniStatus:
    configured: bool
    enabled: bool
    reachable: bool | None = None      # None = not probed
    pipeline_id: str = ""
    detail: str = ""
    languages: tuple[str, ...] = ()


@dataclass
class _Pipeline:
    """A resolved inference endpoint for one language pair."""
    url: str
    header: str
    token: str
    service_id: str
    fetched_at: float = field(default_factory=time.time)


# The auth call is slow (a second or two) and its answer is stable, so it is
# cached per language pair. Guarded by a lock because the server warms the
# model on a thread while the UI is already serving.
_CACHE: dict[tuple[str, str, str], _Pipeline] = {}
_LOCK = threading.Lock()
CACHE_TTL = 60 * 30


# ------------------------------------------------------------------ config ---
def credentials() -> tuple[str, str]:
    return (os.environ.get("BHASHINI_USER_ID", "").strip(),
            os.environ.get("BHASHINI_API_KEY", "").strip())


def pipeline_id() -> str:
    return os.environ.get("BHASHINI_PIPELINE_ID", "").strip() or DEFAULT_PIPELINE


def configured() -> bool:
    return all(credentials())


def enabled() -> bool:
    """On only when someone has deliberately configured it.

    Two conditions, and both are deliberate acts: credentials had to be
    obtained and set, and AYURLEX_BHASHINI=0 has to be absent. There is no
    default-on path and no prompt -- a user who has not configured Bhashini
    never has their question leave the machine.
    """
    return configured() and os.environ.get("AYURLEX_BHASHINI", "1") != "0"


def status(*, probe: bool = False) -> BhashiniStatus:
    """What state the integration is in, for the health endpoint and the CLI."""
    if not configured():
        return BhashiniStatus(
            False, False,
            detail="not configured — set BHASHINI_USER_ID and BHASHINI_API_KEY "
                   "to route translation through Bhashini; without them "
                   "everything stays on this machine",
        )
    if not enabled():
        return BhashiniStatus(
            True, False, pipeline_id=pipeline_id(),
            detail="configured but switched off by AYURLEX_BHASHINI=0",
        )
    st = BhashiniStatus(True, True, pipeline_id=pipeline_id(),
                        languages=tuple(sorted(SUPPORTED)))
    if probe:
        try:
            _resolve("hi", "en")
            st.reachable = True
            st.detail = "reachable"
        except Exception as e:                       # network dependent
            st.reachable = False
            st.detail = f"unreachable: {e}"
    return st


# ------------------------------------------------------------------- http ---
def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _resolve(src: str, tgt: str, *, timeout: float = 20.0) -> _Pipeline:
    """Ask ULCA which service to call for this language pair.

    The auth response carries the endpoint, the header NAME to authenticate
    with (it is not always "Authorization") and the serviceId that the
    inference call has to echo back. Guessing any of the three returns a 401
    that reads like a translation failure, so all three are read from the
    response.
    """
    user, key = credentials()
    if not (user and key):
        raise BhashiniUnavailable("Bhashini credentials are not configured")

    cache_key = (src, tgt, pipeline_id())
    with _LOCK:
        hit = _CACHE.get(cache_key)
        if hit and time.time() - hit.fetched_at < CACHE_TTL:
            return hit

    body = {
        "pipelineTasks": [{
            "taskType": "translation",
            "config": {"language": {"sourceLanguage": src,
                                    "targetLanguage": tgt}},
        }],
        "pipelineRequestConfig": {"pipelineId": pipeline_id()},
    }
    data = _post(AUTH_URL, body, {"userID": user, "ulcaApiKey": key}, timeout)

    try:
        ep = data["pipelineInferenceAPIEndPoint"]
        api_key = ep["inferenceApiKey"]
        service_id = data["pipelineResponseConfig"][0]["config"][0]["serviceId"]
        pipe = _Pipeline(url=ep["callbackUrl"], header=api_key["name"],
                         token=api_key["value"], service_id=service_id)
    except (KeyError, IndexError, TypeError) as e:
        raise BhashiniUnavailable(
            f"unexpected pipeline-config response from ULCA ({e})") from e

    with _LOCK:
        _CACHE[cache_key] = pipe
    return pipe


def translate(text: str, src: str, tgt: str, *, timeout: float = 30.0) -> str:
    """One translation. Raises BhashiniUnavailable rather than returning junk.

    Every caller in this codebase treats a raised exception as "fall back to
    the local path", so failing loudly here is what keeps a network hiccup from
    becoming a silently untranslated answer.
    """
    if not text.strip():
        return ""
    if src == tgt:
        return text
    for code in (src, tgt):
        if code not in SUPPORTED:
            raise BhashiniUnavailable(f"Bhashini does not serve {code!r}")

    pipe = _resolve(src, tgt, timeout=timeout)
    body = {
        "pipelineTasks": [{
            "taskType": "translation",
            "config": {
                "language": {"sourceLanguage": src, "targetLanguage": tgt},
                "serviceId": pipe.service_id,
            },
        }],
        "inputData": {"input": [{"source": text}]},
    }
    try:
        data = _post(pipe.url, body, {pipe.header: pipe.token}, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # A stale cached endpoint looks exactly like a network failure, so the
        # one retry re-resolves rather than repeating the same call.
        with _LOCK:
            _CACHE.pop((src, tgt, pipeline_id()), None)
        raise BhashiniUnavailable(f"Bhashini request failed: {e}") from e

    try:
        out = data["pipelineResponse"][0]["output"][0]["target"]
    except (KeyError, IndexError, TypeError) as e:
        raise BhashiniUnavailable(
            f"unexpected inference response from Bhashini ({e})") from e
    if not isinstance(out, str) or not out.strip():
        raise BhashiniUnavailable("Bhashini returned an empty translation")
    return out.strip()


# --------------------------------------------------------------- masking ----
# Bhashini is a real NMT system, which means it does what NMT systems do: it
# translates "Section 21" into the target language. That is precisely what the
# terminology lock forbids -- a user who copies "பிரிவு 21" onto a form has been
# harmed by the translation -- and the guard in rag/translate.py would reject
# every localised answer for it.
#
# So the immutable tokens are lifted out before the text is sent and put back
# afterwards. The placeholder is bare ASCII with no punctuation because that is
# what survives an NMT pass intact; anything bracketed or symbolic gets
# rewritten or dropped. This makes the invariant hold by construction rather
# than by inspection, and the guards still run afterwards to catch a mask the
# service loses.
MASK = "SAKTIREF{}X"
_MASK_RE = re.compile(r"SAKTIREF\s*(\d{1,3})\s*X", re.I)


def protect(text: str, tokens: list[str]) -> tuple[str, dict[str, str]]:
    """Replace each token with a mask NMT will carry through untouched.

    Longest first, so that masking "Section 21" does not leave a bare "21"
    behind from an earlier, shorter match.
    """
    mapping: dict[str, str] = {}
    out = text
    for i, tok in enumerate(sorted(set(tokens), key=len, reverse=True)):
        if tok not in out:
            continue
        mask = MASK.format(i)
        out = out.replace(tok, mask)
        mapping[mask] = tok
    return out, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put the protected tokens back.

    The tolerant regex is not decoration: a translator that keeps the mask will
    still sometimes respace it or change its case, and "SAKTIREF 3 x" left in
    an answer is worse than either the token or a rejection.
    """
    out = text
    for mask, tok in mapping.items():
        out = out.replace(mask, tok)

    def _fix(m: re.Match) -> str:
        return mapping.get(MASK.format(int(m.group(1))), m.group(0))

    return _MASK_RE.sub(_fix, out)
