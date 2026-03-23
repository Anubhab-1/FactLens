import asyncio
import os
import sys
from pathlib import Path

# Add backend to sys.path for direct imports
backend_path = Path("c:/Users/anubhab samanta/OneDrive/Documents/Desktop/FactLens/factlens/backend")
sys.path.append(str(backend_path))

from pipeline.extractor import extract_claims
from pipeline.retriever import retrieve_evidence
from pipeline.verifier import verify_claim

async def run_diagnostics():
    test_cases = [
        {
            "name": "Simple False Claim (Lyon)",
            "text": "The capital of France is Lyon."
        }
    ]

    print("=== FACTLENS PIPELINE DIAGNOSTICS ===\n")

    for case in test_cases:
        print(f"--- Running Test: {case['name']} ---")
        print(f"Input Text: {case['text']}")

        # 1. Extraction
        print("Extracting claims...")
        claims = await extract_claims(case["text"])
        print(f"Extracted {len(claims)} claims:")
        for c in claims:
            print(f"  - [{c['claim_type']}] {c['claim']}")

        # 2. Retrieval & Verification for each claim
        for c in claims:
            print(f"\nProcessing Claim: {c['claim']}")
            
            print("Retrieving evidence...")
            evidence = await retrieve_evidence(c)
            print(f"Retrieved {len(evidence['sources'])} sources.")

            print("Verifying claim...")
            result = await verify_claim(c, evidence)
            
            print(f"VERDICT: {result['verdict']}")
            print(f"CONFIDENCE: {result['confidence']}")
            print(f"REASONING: {result['reasoning']}")
            
            import json
            # Remove some heavy fields for readability
            debug_result = {k: v for k, v in result.items() if k not in ['evidence_used', 'evidence_provenance', 'supporting_evidence', 'conflicting_evidence', 'mixed_evidence', 'neutral_evidence']}
            print("--- DEBUG RESULT (EXCL EVIDENCE) ---")
            print(json.dumps(debug_result, indent=2))
            
            if result['risk_flags']:
                print("RISK FLAGS:")
                for flag in result['risk_flags']:
                    print(f"  ! {flag}")
        
        print("\n" + "="*40 + "\n")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
