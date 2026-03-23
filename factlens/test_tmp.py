import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import traceback
import unittest
from backend.tests.test_scoring import ScoringTests

try:
    test = ScoringTests('test_verify_claim_blocks_reflection_from_forcing_false_without_direct_evidence')
    test.setUp()
    test.test_verify_claim_blocks_reflection_from_forcing_false_without_direct_evidence()
    print("SUCCESS")
except Exception as e:
    traceback.print_exc()
