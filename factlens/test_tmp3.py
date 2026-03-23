import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from pipeline.retriever import _build_source_record, _recovery_reasons
from pipeline.scoring import domain_authority_score

print("Auth score for reuters.com:", domain_authority_score("reuters.com"))
claim = {
    "id": "1",
    "claim": "The current CEO of ExampleCorp is Jane Doe.",
    "claim_type": "entity",
    "time_sensitive": True,
}
result = {
    "url": "https://reuters.com/leadership",
    "title": "Leadership team",
    "content": "Jane Doe is the current CEO of ExampleCorp as of March 2026.",
    "published_date": "2026-03-15",
}
query = {"objective": "recency", "phase": "recovery"}
source = _build_source_record(claim, result, query)
print("Source:", source["authority_score"], source["relevance_score"], source["overall_score"])
print("Reasons:", _recovery_reasons(claim, [source]))
