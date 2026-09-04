"""Retrieval gold set. Small, honest, and run in CI.

Not the 300-item evaluation the build plan calls for -- this is the seed of it.
Each case names the provision a domain reader would expect, so a regression in
the concept lexicon or the reranker shows up as a number rather than as a vibe.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLD: list[tuple[str, str | None]] = [
    ("Can I patent a traditional ayurvedic formulation?", "IN.PATENTS.1970::S3"),
    ("can I mix two known herbs and patent the combination", "IN.PATENTS.1970::S3"),
    ("is my polyherbal blend an invention", "IN.PATENTS.1970::S3"),
    ("Do I need permission before applying for a patent using Indian plants?",
     "IN.BDA.2002::S6"),
    ("do I need NBA approval", "IN.BDA.2002::S6"),
    ("I am a vaidya, do I need to inform the state biodiversity board",
     "IN.BDA.2002::S7"),
    ("benefit sharing for use of biological resources", "IN.BDA.2002::S21"),
    ("can I advertise that my product cures diabetes", "IN.DMR.1954::S3"),
    ("is it legal to claim my churna treats epilepsy", "IN.DMR.1954::S3"),
    ("is my advertisement misleading", "IN.DMR.1954::S4"),
    ("what stops someone from registering a brand name that is just descriptive",
     "IN.TM.1999::S9"),
    ("I want to file a patent abroad first, is that allowed", "IN.PATENTS.1970::S39"),
    ("can I file in America before India", "IN.PATENTS.1970::S39"),
    ("must I disclose where the plant material came from", "IN.PATENTS.1970::S10"),
    ("do I have to tell the controller about my foreign applications",
     "IN.PATENTS.1970::S8"),
    ("how do I get a GI tag for a regional product", "IN.GI.1999::S9"),
    ("क्या मैं गिलोय का पेटेंट करा सकता हूँ", "IN.PATENTS.1970::S3"),
    # Unanswerable by design: nothing in the ingested corpus covers US law.
    ("what is the US filing fee for a provisional application", None),
    ("how long does EPO opposition take", None),
]


def evaluate(verbose: bool = True) -> dict:
    from rag.retriever import load_retriever

    r = load_retriever()
    at1 = at5 = answerable = 0
    abstain_ok = abstain_total = 0
    misses = []

    for q, want in GOLD:
        res = r.search(q, k=5)
        ids = [h.corpus_id.split("#")[0] for h in res.hits]
        if want is None:
            abstain_total += 1
            # Correct behaviour is a weak-retrieval abstention.
            if res.is_weak:
                abstain_ok += 1
            else:
                misses.append((q, "should have abstained", ids[:2]))
            continue
        answerable += 1
        rank = ids.index(want) + 1 if want in ids else None
        if rank:
            at5 += 1
            if rank == 1:
                at1 += 1
        else:
            misses.append((q, want, ids[:3]))

    out = {
        "recall@1": at1 / answerable,
        "recall@5": at5 / answerable,
        "abstention_accuracy": abstain_ok / max(abstain_total, 1),
        "answerable": answerable,
        "misses": misses,
    }
    if verbose:
        print(f"  recall@1            {out['recall@1']:.2f}  ({at1}/{answerable})")
        print(f"  recall@5            {out['recall@5']:.2f}  ({at5}/{answerable})")
        print(f"  abstention accuracy {out['abstention_accuracy']:.2f}  "
              f"({abstain_ok}/{abstain_total})")
        for q, want, got in misses:
            print(f"    MISS  {q[:58]:<60} want={want} got={got}")
    return out


if __name__ == "__main__":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    print("SAMHITA retrieval gold set\n")
    evaluate()
