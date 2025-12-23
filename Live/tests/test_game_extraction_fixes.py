"""
Test script to verify game name extraction fixes for problematic titles
"""
from bot.integrations.igdb import calculate_confidence
from bot.utils.text_processing import extract_game_name_from_title
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Live'))


# Test cases from actual logs
test_cases = [
    {
        'title': 'Horror + Monsters + Space + Me Screaming = Cronos: A New Dawn',
        'expected': 'Cronos: A New Dawn',
        'description': 'Creative title with = separator'
    },
    {
        'title': "I'm not scared, YOU ARE! - Cronos: A New Dawn (First Playthrough day 5)",
        'expected': 'Cronos: A New Dawn',
        'description': 'Episode title before game name with (day X)'
    },
    {
        'title': "The Terror of Space - Cronos: A New Dawn (First Playthrough day 3) [gift]",
        'expected': 'Cronos: A New Dawn',
        'description': 'Episode title with [gift] tag'
    },
    {
        'title': 'Samurai School Dropout - Ghost of Yotei (day 9) Thanks @playstation #ad/gift',
        'expected': 'Ghost of Yotei',
        'description': 'Episode title with sponsors'
    },
    {
        'title': 'Resident Evil 8 Village [day 8]',
        'expected': 'Resident Evil 8 Village',
        'description': '[day X] should be removed'
    },
    {
        'title': 'End Game?',
        'expected': None,  # Too short/generic
        'description': 'Should reject short exclamatory phrases'
    },
    {
        'title': "I'm not scared, you are",
        'expected': None,  # Episode title without game marker
        'description': 'Should reject episode titles without game context'
    }
]

# Test IGDB confidence with article differences
igdb_confidence_tests = [
    {
        'extracted': 'Cronos: A New Dawn',
        'igdb': 'Cronos: The New Dawn',
        'expected_confidence': 0.95,
        'description': 'Article difference (A vs The)'
    },
    {
        'extracted': 'Ghost of Yotei',
        'igdb': 'Ghost of Yōtei',
        'expected_confidence': 0.85,  # High but not perfect due to special char
        'description': 'Special character difference'
    },
    {
        'extracted': 'Silent Hill f',
        'igdb': 'Silent Hill f',
        'expected_confidence': 1.0,
        'description': 'Exact match'
    }
]

print("=" * 80)
print("GAME NAME EXTRACTION TESTS")
print("=" * 80)

passed = 0
failed = 0

for i, test in enumerate(test_cases, 1):
    extracted = extract_game_name_from_title(test['title'])
    expected = test['expected']

    status = "✅ PASS" if extracted == expected else "❌ FAIL"
    if extracted == expected:
        passed += 1
    else:
        failed += 1

    print(f"\nTest {i}: {test['description']}")
    print(f"  Title:    {test['title']}")
    print(f"  Expected: {expected}")
    print(f"  Got:      {extracted}")
    print(f"  {status}")

print("\n" + "=" * 80)
print("IGDB CONFIDENCE TESTS")
print("=" * 80)

for i, test in enumerate(igdb_confidence_tests, 1):
    confidence = calculate_confidence(test['extracted'], test['igdb'])
    expected = test['expected_confidence']

    # Allow small tolerance for floating point
    matches = abs(confidence - expected) < 0.1
    status = "✅ PASS" if matches else "❌ FAIL"

    if matches:
        passed += 1
    else:
        failed += 1

    print(f"\nTest {i}: {test['description']}")
    print(f"  Extracted: {test['extracted']}")
    print(f"  IGDB:      {test['igdb']}")
    print(f"  Expected:  {expected:.2f}")
    print(f"  Got:       {confidence:.2f}")
    print(f"  {status}")

print("\n" + "=" * 80)
print(f"SUMMARY: {passed} passed, {failed} failed")
print("=" * 80)
