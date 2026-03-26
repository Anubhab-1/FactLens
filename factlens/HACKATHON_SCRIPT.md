# FactLens Hackathon Script

## 2-Minute Main Script

Good morning, ma'am.

Our project is **FactLens**.

The problem we are solving is that today people consume a huge amount of information from articles, social posts, and AI-generated text, but most tools either give a single yes-or-no answer or they do not show how that answer was reached.

**FactLens** is a claim verification platform that takes a block of text or a URL, breaks it into atomic claims, searches for live evidence, and then produces a claim-by-claim report with verdicts, citations, confidence, and risk flags.

The key idea is that we do **not** trust a one-shot AI answer.
Instead, our pipeline works in stages.

First, we extract claims from the input.
Second, the user can review and edit those claims before verification.
Third, the backend retrieves evidence from the web using multiple search strategies.
If the first retrieval is weak, the system automatically repairs the search query and retries.
Finally, the engine compares supporting and conflicting evidence and assigns a calibrated verdict like **TRUE**, **FALSE**, **PARTIALLY TRUE**, or **UNVERIFIABLE**.

What makes this project different is transparency.
We show:
- the extracted claims,
- the original source text,
- the evidence passages used,
- why sources disagree,
- whether the evidence is stale,
- and confidence signals for each result.

So instead of just saying "this is false," FactLens shows **why** it thinks that, and what evidence was used.

On the technical side, the frontend is built with **React and Vite**, and the backend uses **FastAPI**.
The pipeline includes claim extraction, retrieval, evidence grounding, verdict scoring, report storage, and export features like **shareable links, JSON export, and PDF export**.

In short, FactLens helps users move from blind trust to evidence-based verification.

Thank you. I will now show the demo.

---

## 60-Second Short Version

Good morning, ma'am.

Our project, **FactLens**, is an AI-assisted fact-checking platform.
It takes text or a URL, extracts individual claims, finds live supporting and conflicting evidence, and generates a structured verification report.

The main difference is that FactLens does not give a black-box answer.
It lets the user review extracted claims, shows the exact evidence passages, explains conflict reasons, and marks whether a claim is true, false, partially true, or unverifiable.

Technically, we built it using **React** on the frontend and **FastAPI** on the backend, with a multi-stage verification pipeline for claim extraction, retrieval, and verdict calibration.

So the value of FactLens is not just automation, but **transparent and explainable fact verification**.

---

## Demo Script

Here I will paste a text or article URL into FactLens.

First, the system extracts the important factual claims from the content.
If needed, I can manually review and edit them before verification.

Next, FactLens searches for evidence from multiple sources.
It does not stop at one result; it tries to recover from weak or noisy searches.

After that, the report is generated.
For each claim, we can see:
- the verdict,
- confidence,
- supporting evidence,
- conflicting evidence,
- and the exact evidence passages used in the decision.

This makes the result more trustworthy, because the user can inspect the reasoning instead of blindly accepting an AI answer.

---

## What To Say If Asked "What Is Innovative Here?"

Our innovation is in the workflow, not just the model.

Most fact-checking demos ask an LLM for one final answer.
We instead use a transparent pipeline:
- claim extraction,
- human review,
- retrieval repair,
- grounded evidence comparison,
- and calibrated verdict scoring.

So the system is more explainable, easier to audit, and more useful in real-world ambiguous cases.

---

## What To Say If Asked "Why Is This Useful?"

This is useful for students, journalists, researchers, and even general users who want to verify claims before sharing them.

It is especially relevant now because AI-generated content and misinformation are increasing rapidly.
FactLens helps users verify not just whether a statement looks correct, but whether it is backed by real evidence.

---

## What To Say If Asked "What Are The Current Limitations?"

Right now, the system depends on retrieval quality, so live web evidence can vary depending on source availability.
Also, some claims are inherently ambiguous or time-sensitive, so the system may return **PARTIALLY TRUE** or **UNVERIFIABLE** instead of forcing a wrong answer.

We consider that a strength, because we prefer honest uncertainty over false confidence.

---

## Strong Closing Line

FactLens is not just a fact-checker.
It is an **explainable verification system** that helps users understand what to trust, why to trust it, and where uncertainty still remains.
