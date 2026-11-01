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


# Dev set. Written as a held-out set (lay phrasing, without looking at the
# concept lexicon), scored 0.50 recall@5, and THEN used to fix retrieval -- so
# it is no longer held out. It stays as a regression set.
# Three labels were widened after review where a second section is equally
# correct law (S64 revocation, TM S135 relief, Designs S21 exhibitions).
DEV: list[tuple[str, str | tuple[str, ...] | None]] = [
    # Patents Act, 1970
    ("what does the law count as an invention", "IN.PATENTS.1970::S2"),
    ("when will my patent application become public", "IN.PATENTS.1970::S11A"),
    ("a competitor got a patent on my product, how do I challenge it",
     ("IN.PATENTS.1970::S25", "IN.PATENTS.1970::S64")),  # opposition or revocation
    ("what exactly can I stop others from doing once I have a patent",
     "IN.PATENTS.1970::S48"),
    ("how many years does an Indian patent last", "IN.PATENTS.1970::S53"),
    ("on what grounds can a granted patent be cancelled", "IN.PATENTS.1970::S64"),
    ("can the government make me license my patent to someone else",
     "IN.PATENTS.1970::S84"),
    ("I filed in another country last month, can I use that date in India",
     "IN.PATENTS.1970::S135"),
    # Trade Marks Act, 1999
    ("someone already has a brand that sounds like mine, can I still register",
     "IN.TM.1999::S11"),
    ("how do I apply to register my brand name", "IN.TM.1999::S18"),
    ("how long is a trademark registration valid before renewal",
     "IN.TM.1999::S25"),
    ("another company is selling herbal oil under my registered brand",
     ("IN.TM.1999::S29", "IN.TM.1999::S135")),  # infringement, or its relief
    # Geographical Indications Act, 1999
    ("who can apply to register a geographical indication", "IN.GI.1999::S11"),
    ("how long does a GI registration stay in force", "IN.GI.1999::S18"),
    ("a seller outside the region uses our GI name, is that infringement",
     "IN.GI.1999::S22"),
    # Biological Diversity Act, 2002
    ("can a foreign company collect medicinal plants in India for research",
     "IN.BDA.2002::S3"),
    ("can I share my research results on Indian herbs with a foreign lab",
     "IN.BDA.2002::S4"),
    ("are commonly traded herbs exempt from biodiversity approvals",
     "IN.BDA.2002::S40"),
    ("what is the punishment for breaking the biodiversity law",
     "IN.BDA.2002::S55"),
    # Drugs and Magic Remedies Act, 1954
    ("can I sell an amulet that promises to cure illness", "IN.DMR.1954::S5"),
    ("what happens if I publish a banned medical advertisement",
     "IN.DMR.1954::S7"),
    # Copyright, Designs, PPV&FR
    ("what rights does copyright give me over my ayurveda textbook",
     "IN.COPYRIGHT.1957::S14"),
    ("how long does copyright in a book last", "IN.COPYRIGHT.1957::S22"),
    ("can I register a bottle design that I already showed at an exhibition",
     ("IN.DESIGNS.2000::S4", "IN.DESIGNS.2000::S21")),  # s.21: exhibitions
    ("how long is a registered design protected", "IN.DESIGNS.2000::S11"),
    ("can a farmer save and sell seeds of a protected variety",
     "IN.PPVFR.2001::S39"),
    ("how do I register a new plant variety", "IN.PPVFR.2001::S14"),
    # Food Safety and Standards Act, 2006
    ("do I need a licence to sell a herbal food product", "IN.FSSA.2006::S31"),
    ("how are nutraceuticals and functional foods regulated",
     "IN.FSSA.2006::S22"),
    ("rules on misleading advertisements for food products",
     "IN.FSSA.2006::S24"),
    # Out of corpus: must abstain.
    ("how do I register a trademark in Japan", None),
    ("what does the UK require to register a traditional herbal medicine", None),
    ("how much does a Chinese utility model cost", None),
]


# Held-out set, v2. Written BEFORE the dev-set fixes and not run until they
# were finished; it must never be tuned against. Where two sections are both
# a correct legal answer, either counts. Out-of-scope items cover foreign law,
# off-topic, clinical and evasion questions -- all must abstain.
# When this set has been looked at and fixed against, demote it to DEV and
# write a new one.
HELD_OUT: list[tuple[str, str | tuple[str, ...] | None]] = [
    # Patents Act, 1970
    ("the patent office rejected my application, can I appeal",
     "IN.PATENTS.1970::S117A"),
    ("what must I include when I describe my invention in the application",
     "IN.PATENTS.1970::S10"),
    ("who is allowed to apply for a patent", "IN.PATENTS.1970::S6"),
    ("can a university use my patented process for research without asking",
     ("IN.PATENTS.1970::S47", "IN.PATENTS.1970::S107A")),
    ("what can a court order if someone copies my patented product",
     ("IN.PATENTS.1970::S108", "IN.PATENTS.1970::S104", "IN.PATENTS.1970::S48")),
    ("is there a deadline to ask the patent office to examine my application",
     "IN.PATENTS.1970::S11B"),
    ("what happens to my patent if I stop paying renewal fees",
     "IN.PATENTS.1970::S53"),
    # Trade Marks Act, 1999
    ("can I trademark an ordinary word like herbal", "IN.TM.1999::S9"),
    ("a mark like mine was registered after I started using mine, how do I get it removed",
     ("IN.TM.1999::S57", "IN.TM.1999::S47")),
    ("can I let a distributor use my registered trademark",
     ("IN.TM.1999::S48", "IN.TM.1999::S49")),
    ("what is the punishment for selling fake branded goods",
     ("IN.TM.1999::S102", "IN.TM.1999::S103", "IN.TM.1999::S104")),
    # Geographical Indications Act, 1999
    ("can a common generic name be registered as a GI", "IN.GI.1999::S9"),
    ("what is the penalty for faking a GI label",
     ("IN.GI.1999::S38", "IN.GI.1999::S39", "IN.GI.1999::S40")),
    ("how does a producer become an authorised user of a GI", "IN.GI.1999::S17"),
    # Biological Diversity Act, 2002
    ("does an Indian company have to inform the state board before using bio resources commercially",
     "IN.BDA.2002::S7"),
    ("what is the penalty for using biological resources without NBA approval",
     "IN.BDA.2002::S55"),
    ("are joint research projects with foreign institutes exempt from NBA approval",
     "IN.BDA.2002::S5"),
    ("how is the benefit sharing amount decided", "IN.BDA.2002::S21"),
    # Drugs and Magic Remedies Act, 1954
    ("can I advertise a herbal medicine for improving sexual performance",
     "IN.DMR.1954::S3"),
    ("if a company publishes a banned drug advertisement, who is liable",
     ("IN.DMR.1954::S9", "IN.DMR.1954::S7")),
    # Copyright Act, 1957
    ("do I have to register copyright in my recipe book",
     "IN.COPYRIGHT.1957::S45"),
    ("who owns the copyright in a book written by an employee",
     "IN.COPYRIGHT.1957::S17"),
    ("what counts as copyright infringement",
     ("IN.COPYRIGHT.1957::S51", "IN.COPYRIGHT.1957::S63")),
    # Designs Act, 2000
    ("what kinds of designs cannot be registered", "IN.DESIGNS.2000::S4"),
    ("how do I extend protection of a registered design after ten years",
     "IN.DESIGNS.2000::S11"),
    ("someone copied my registered packaging design, what can I do",
     "IN.DESIGNS.2000::S22"),
    # PPV&FR Act, 2001
    ("who can apply to protect a plant variety", "IN.PPVFR.2001::S16"),
    ("can a farmer register a variety he developed himself",
     ("IN.PPVFR.2001::S14", "IN.PPVFR.2001::S39", "IN.PPVFR.2001::S16")),
    # Food Safety and Standards Act, 2006
    ("do I need FSSAI registration for a small home food business",
     "IN.FSSA.2006::S31"),
    ("what is the punishment for selling unsafe food", "IN.FSSA.2006::S59"),
    ("what happens if I run a food business without a licence",
     "IN.FSSA.2006::S63"),
    # Out of scope: must abstain.
    ("how long does a patent last in Brazil", None),
    ("what is the trademark registration fee in Singapore", None),
    ("how do I get my herbal product approved by Health Canada", None),
    ("can you recommend a good restaurant in Delhi", None),
    ("explain the theory of relativity", None),
    ("who is the prime minister of India", None),
    ("what dose of brahmi should I give my child", None),
    ("how do I sell ayurvedic medicine without a licence and avoid the inspectors", None),
]


def evaluate(verbose: bool = True, cases=None) -> dict:
    from rag.retriever import load_retriever

    r = load_retriever()
    at1 = at5 = answerable = 0
    abstain_ok = abstain_total = 0
    misses = []

    for q, want in (GOLD if cases is None else cases):
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
        wants = (want,) if isinstance(want, str) else want
        ranks = [ids.index(w) + 1 for w in wants if w in ids]
        rank = min(ranks) if ranks else None
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
    print("\nHeld-out set (not tuned against)\n")
    evaluate(cases=HELD_OUT)
