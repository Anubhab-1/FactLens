import re
import sys
import os

# Set paths
sys.path.append(os.path.abspath('.'))

from pipeline.extractor import _normalize_text, _split_candidate_sentences
from pipeline.scoring import classify_claim_type

def run_verify():
    with open('verify_mona_lisa.log', 'w', encoding='utf-8') as f:
        f.write("MONA LISA / WIKIPEDIA LOGIC VERIFICATION\n")
        f.write("========================================\n\n")

        # Case 1: Alphabetic and Special Tags
        test_text = "The Mona Lisa[a] is a painting.[b] It was equivalent to $1 billion as of 2023[update].[15] Title and subject The title is Monna Lisa."
        
        f.write("1. Testing Universal Stripping ([a], [update], etc.)\n")
        normalized = _normalize_text(test_text)
        f.write(f"Result: {normalized}\n")
        if re.search(r"\[[a-z]|update\]", normalized):
            f.write("STATUS: FAILED (Wikipedia tags remained)\n\n")
        else:
            f.write("STATUS: PASSED\n\n")

        # Case 2: Classification Priority (1519 as Date)
        f.write("2. Testing Classification Priority (Year as Date)\n")
        year_claim = "King Francis I acquired the painting in 1519."
        ctype = classify_claim_type(year_claim)
        f.write(f"Claim: {year_claim}\n")
        f.write(f"Type: {ctype}\n")
        if ctype == "date":
            f.write("STATUS: PASSED\n\n")
        else:
            f.write(f"STATUS: FAILED (Got {ctype}, expected date)\n\n")

        # Case 3: Footnote stripped from classification
        f.write("3. Testing Footnote stripping in Classification\n")
        footnote_claim = "The Mona Lisa[a] is a masterwork.[4][5]"
        ctype2 = classify_claim_type(footnote_claim)
        f.write(f"Claim: {footnote_claim}\n")
        f.write(f"Type: {ctype2}\n")
        if ctype2 == "entity":
            f.write("STATUS: PASSED\n\n")
        else:
            f.write(f"STATUS: FAILED (Got {ctype2}, expected entity)\n\n")

        # Case 4: Robust Splitting (Period citation next sentence)
        f.write("4. Testing Robust Splitting\n")
        merged_text = "Revolution.[3][4]Next sentence starts here."
        parts = _split_candidate_sentences(_normalize_text(merged_text))
        f.write(f"Sentences found: {len(parts)}\n")
        for i, p in enumerate(parts):
            f.write(f"  {i+1}: {p}\n")
        if len(parts) >= 2:
            f.write("STATUS: PASSED\n")
        else:
            f.write("STATUS: FAILED (Did not split merged sentences)\n")

if __name__ == "__main__":
    run_verify()
