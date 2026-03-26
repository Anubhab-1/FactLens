import re
import sys
import os

# Mocking the functions to test them in isolation if needed, 
# but better to import them directly if paths allow.

# Set paths
sys.path.append(r'c:\Users\anubhab samanta\OneDrive\Documents\Desktop\FactLens\factlens\backend')

from pipeline.extractor import _normalize_text, _split_candidate_sentences
from pipeline.scoring import classify_claim_type

def test():
    test_text = "The rise in temperatures is driven by human activities, especially fossil fuel burning since the Industrial Revolution.[3][4] Fossil fuel use, deforestation, and some agricultural and industrial practices release greenhouse gases.[5] These gases absorb some of the heat that the Earth radiates after it warms from sunlight, warming the lower atmosphere."
    
    print("--- Test 1: Normalize Text (Citation Stripping) ---")
    normalized = _normalize_text(test_text)
    print(f"Normalized: {normalized}")
    if "[" in normalized or "]" in normalized:
        print("FAILED: Citations found in normalized text")
    else:
        print("PASSED: Citations stripped")

    print("\n--- Test 2: Sentence Splitting ---")
    # Note: _split_candidate_sentences uses normalized text
    parts = _split_candidate_sentences(normalized)
    print(f"Found {len(parts)} sentences.")
    for i, p in enumerate(parts):
        print(f"  {i+1}: {p}")
    
    if len(parts) >= 3:
        print("PASSED: Successfully split 3 sentences")
    else:
        print("FAILED: Did not split sentences correctly")

    print("\n--- Test 3: Claim Classification ---")
    # The problematic claim from user JSON
    bad_claim = "The modern-day rise in global temperatures is driven by human activities, especially fossil fuel (coal, oil and natural gas) burning since the Industrial Revolution.[3][4]"
    ctype = classify_claim_type(bad_claim)
    print(f"Claim: {bad_claim}")
    print(f"Type: {ctype}")
    if ctype == "numeric":
        print("FAILED: Still classified as numeric due to [3][4]")
    else:
        print(f"PASSED: Classified as {ctype}")

if __name__ == "__main__":
    test()
