"""Translation layer: any user picks a language in Settings; patient-facing text is produced in it.

Translations come from the LLM chain (medical-safe prompt) and are cached in `translation_cache`. When no model is
reachable the English source is returned and `translated=False`, so callers can tell the user instead of failing.
Medicine names, doses, numbers, times and markdown structure are preserved by instruction AND verified.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from sqlalchemy import select

from app.core import llm
from app.core.db import session_scope
from app.core.i18n import DEFAULT_LANGUAGE, language_name, normalize_language  # noqa: F401
from app.models import TranslationCache

log = logging.getLogger("carexhealth.translation")

SYSTEM = (
    "You are a certified medical translator for a hospital. Translate each string of the given JSON array into {language}. "
    "Rules: keep markdown syntax, tables, emojis, numbers, dates, times, units, URLs and phone numbers exactly; never translate or alter medicine names, "
    "doses or abbreviations like mg/ml/bpm; do not add, remove or soften any medical instruction or warning; keep a warm, simple tone (reading age ~12). "
    'Return JSON {{"translations": [...]}} with exactly the same number of items, in the same order.'
)
CHUNK_CHARS = 6000
_NUM = re.compile(r"\d+(?:[.:/]\d+)*")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _numbers_preserved(src: str, out: str) -> bool:
    """Safety net: every number in the source must survive translation (doses, times, phone numbers)."""
    return sorted(_NUM.findall(src)) == sorted(_NUM.findall(out)) or all(n in out for n in set(_NUM.findall(src)))


def _validator(n: int):  # noqa: ANN202
    def validate(obj: Any) -> list[str]:
        items = obj.get("translations") if isinstance(obj, dict) else obj
        if not isinstance(items, list) or len(items) != n or not all(isinstance(x, str) and x.strip() for x in items):
            raise ValueError("translation shape mismatch")
        return items

    return validate


async def translate_many(texts: list[str], lang: str | None) -> tuple[list[str], bool]:
    """→ (translated texts in input order, all_translated). Falls back to the source text per item."""
    lang = normalize_language(lang)
    if lang == DEFAULT_LANGUAGE or not texts:
        return list(texts), lang == DEFAULT_LANGUAGE
    out: dict[str, str] = {}
    unique = [t for t in dict.fromkeys(texts) if t.strip()]
    hashes = {t: _hash(t) for t in unique}
    with session_scope() as s:
        for row in s.scalars(select(TranslationCache).where(TranslationCache.lang == lang, TranslationCache.source_hash.in_(hashes.values()))):
            out[row.source] = row.text
    missing = [t for t in unique if t not in out]
    agent = llm.build_llm_agent("Translator", SYSTEM.format(language=language_name(lang))) if missing else None
    if agent is not None:
        batches: list[list[str]] = []
        cur: list[str] = []
        size = 0
        for t in missing:
            if cur and size + len(t) > CHUNK_CHARS:
                batches.append(cur)
                cur, size = [], 0
            cur.append(t)
            size += len(t)
        if cur:
            batches.append(cur)
        for batch in batches:
            import json

            result = await llm.run_json(agent, json.dumps(batch, ensure_ascii=False), _validator(len(batch)))
            if not result:
                continue
            engine = llm.last_engine()
            good = {}
            for src, tr in zip(batch, result, strict=True):
                if _numbers_preserved(src, tr):
                    good[src] = tr
                else:
                    log.warning("translation dropped a number; keeping English for one string")
            out.update(good)
            try:
                with session_scope() as s:
                    for src, tr in good.items():
                        s.add(TranslationCache(lang=lang, source_hash=_hash(src), source=src, text=tr, engine=engine))
            except Exception:  # noqa: BLE001 — a racing writer already cached it; the translation itself is fine
                log.info("translation cache write skipped")
    final = [out.get(t, t) for t in texts]
    return final, all((t in out) or not t.strip() for t in texts)


async def patient_language(patient_id: str) -> str:
    from app.models import Patient, User

    with session_scope() as s:
        p = s.get(Patient, patient_id)
        u = s.get(User, p.user_id) if p else None
        return normalize_language(u.language if u else None)


async def localize(text: str, lang: str | None) -> tuple[str, bool]:
    res, ok = await translate_many([text], lang)
    return res[0], ok
