import asyncio
import sys
import os

# Set paths
sys.path.append(os.path.abspath('.'))

from pipeline.extractor import extract_claims_with_metadata

async def test_solar_recall():
    # A dense paragraph of Solar System facts to test recall and domain logic
    solar_text = """
    The Solar System formed 4.568 billion years ago from the gravitational collapse of a region within a large molecular cloud.
    The Sun is a G-type main-sequence star that contains 99.86% of the system's known mass.
    The four smaller inner system planets, Mercury, Venus, Earth and Mars, are terrestrial planets, being primarily composed of rock and metal.
    The four outer system planets are giant planets, being substantially more massive than the terrestrials.
    The two largest, Jupiter and Saturn, are gas giants, being composed mainly of hydrogen and helium.
    The two outermost planets, Uranus and Neptune, are ice giants, being composed mostly of substances with relatively high melting points compared with hydrogen and helium, called volatiles, such as water, ammonia and methane.
    All eight planets have almost circular orbits that lie within a nearly flat disc called the ecliptic.
    There are an unknown number of smaller dwarf planets and innumerable small Solar System bodies.
    Natural satellites, or moons, orbit the planets and other small Solar System bodies.
    The Solar System also contains regions inhabited by smaller objects.
    The asteroid belt, which lies between the orbits of Mars and Jupiter, mostly contains objects composed, like the terrestrial planets, of rock and metal.
    Beyond Neptune's orbit lie the Kuiper belt and scattered disc, which are populations of trans-Neptunian objects composed mostly of ices.
    In these populations are several dozen to possibly tens of thousands of objects large enough that they have been rounded by their own gravity.
    Such objects are categorized as dwarf planets.
    Directly reaching the Sun is possible for a space mission using gravitational assists.
    Viking 1 was the first spacecraft to land on Mars and successfully complete its mission in 1976.
    """

    print("Starting High-Recall Extraction Test...")
    print(f"Input text length: {len(solar_text)} chars")
    
    result = await extract_claims_with_metadata(solar_text)
    claims = result.get("claims", [])
    meta = result.get("meta", {})
    
    print(f"Extracted {len(claims)} claims.")
    print(f"Extraction Mode: {meta.get('mode')}")
    if meta.get('warnings'):
        print(f"Warnings: {meta.get('warnings')}")
    
    with open('solar_recall_results.log', 'w', encoding='utf-8') as f:
        f.write("SOLAR SYSTEM RECALL TEST\n")
        f.write("========================\n\n")
        f.write(f"Total claims: {len(claims)}\n")
        f.write(f"Extraction Mode: {meta.get('mode')}\n")
        f.write(f"Warnings: {meta.get('warnings')}\n\n")
        for c in claims:
            f.write(f"ID {c.get('id')}: {c.get('claim')}\n")
            f.write(f"  Type: {c.get('claim_type')}\n")
            f.write("-" * 20 + "\n")

    if len(claims) > 15:
        print("STATUS: PASSED (High recall achieved)")
    else:
        print(f"STATUS: FAILED (Low recall: only {len(claims)} claims)")

if __name__ == "__main__":
    asyncio.run(test_solar_recall())
