import re
import sys
import os

# Set paths
sys.path.append(os.path.abspath('.'))

from pipeline.extractor import _normalize_text, _split_candidate_sentences
from pipeline.scoring import classify_claim_type

def run_verify():
    with open('verify_results.log', 'w', encoding='utf-8') as f:
        f.write("LOGIC FIX VERIFICATION\n")
        f.write("======================\n\n")

        test_text = "The rise in temperatures is driven by human activities, especially fossil fuel burning since the Industrial Revolution.[3][4] Fossil fuel use, deforestation, and some agricultural and industrial practices release greenhouse gases.[5] These gases absorb some of the heat that the Earth radiates after it warms from sunlight, warming the lower atmosphere."
        
        f.write("1. Testing _normalize_text (Citation Stripping)\n")
        normalized = _normalize_text(test_text)
        f.write(f"Result: {normalized}\n")
        if "[" in normalized:
            f.write("STATUS: FAILED (Brackets remained)\n\n")
        else:
            f.write("STATUS: PASSED\n\n")

        f.write("2. Testing _split_candidate_sentences\n")
        parts = _split_candidate_sentences(normalized)
        f.write(f"Sentences found: {len(parts)}\n")
        for i, p in enumerate(parts):
            f.write(f"  {i+1}: {p}\n")
        if len(parts) == 3:
            f.write("STATUS: PASSED\n\n")
        else:
            f.write("STATUS: FAILED (Expected 3 sentences)\n\n")

        f.write("3. Testing classify_claim_type (Citation exclusion)\n")
        bad_claim = "The modern-day rise in global temperatures is driven by human activities, especially fossil fuel (coal, oil and natural gas) burning since the Industrial Revolution.[3][4]"
        ctype = classify_claim_type(bad_claim)
        f.write(f"Claim: {bad_claim}\n")
        f.write(f"Type: {ctype}\n")
        if ctype == "entity":
            f.write("STATUS: PASSED\n")
        else:
            f.write(f"STATUS: FAILED (Got {ctype}, expected entity)\n")

if __name__ == "__main__":
    run_verify()
