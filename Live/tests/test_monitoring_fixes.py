#!/usr/bin/env python3
"""
Test script to verify the monitoring fixes prevent false positives
Tests both the old problematic patterns and new correct behavior.
"""

import re
import sys
import os

# Add the current directory to Python path so we can import bot modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def is_casual_conversation_not_query(content: str) -> bool:
    """Detect if a message is casual conversation/narrative rather than a query"""
    content_lower = content.lower()
    
    # Patterns that indicate the message is describing past events or casual conversation
    casual_conversation_patterns = [
        r"and then",  # "and then someone recommends"
        r"someone (?:said|says|recommends?|suggested?)",  # "someone recommends Portal"
        r"(?:he|she|they) (?:said|says|recommends?|suggested?)",  # "she said..."
        r"the fact that",  # "the fact that Jam says"
        r"jam says",  # "Jam says remember what games"
        r"remember (?:when|that|what)",  # "remember what games"
        r"i (?:was|am) (?:telling|talking about)",  # "I was telling someone"
        r"we were (?:discussing|talking about)",  # "we were discussing"
        r"yesterday (?:someone|he|she|they)",  # "yesterday someone said"
        r"earlier (?:someone|he|she|they)",  # "earlier they mentioned"
        r"(?:mentioned|talked about|discussed) (?:that|how|what)",  # "mentioned that..."
    ]
    
    return any(re.search(pattern, content_lower) for pattern in casual_conversation_patterns)

def detect_implicit_game_query_fixed(content: str) -> bool:
    """Fixed version - Detect if a message is likely a game-related query even without explicit bot mention"""
    content_lower = content.lower()

    # First check if this is casual conversation rather than a query
    if is_casual_conversation_not_query(content):
        return False

    # Game query patterns - Made more specific to avoid false positives on casual conversation
    game_query_patterns = [
        r"has\s+jonesy\s+played",
        r"did\s+jonesy\s+play",
        r"has\s+captain\s+jonesy\s+played",
        r"did\s+captain\s+jonesy\s+play",
        r"what\s+games?\s+has\s+jonesy",
        r"what\s+games?\s+did\s+jonesy",
        r"which\s+games?\s+has\s+jonesy",
        r"which\s+games?\s+did\s+jonesy",
        r"what.*game.*most.*playtime",
        r"which.*game.*most.*episodes",
        r"what.*game.*longest.*complete",
        # More specific recommendation patterns to avoid casual conversation
        r"^is\s+.+\s+recommended\s*[\?\.]?$",  # Must be at start and end of message
        r"^who\s+recommended\s+.+[\?\.]?$",   # Must be at start and end of message
        r"^what\s+(games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend", # Direct recommendation requests only
        r"jonesy.*gaming\s+(history|database|archive)",
    ]

    return any(re.search(pattern, content_lower) for pattern in game_query_patterns)

def detect_implicit_game_query_old(content: str) -> bool:
    """Old version with overly broad patterns - for comparison"""
    content_lower = content.lower()

    # Game query patterns - overly broad, causes false positives
    game_query_patterns = [
        r"has\s+jonesy\s+played",
        r"did\s+jonesy\s+play",
        r"has\s+captain\s+jonesy\s+played",
        r"did\s+captain\s+jonesy\s+play",
        r"what\s+games?\s+has\s+jonesy",
        r"what\s+games?\s+did\s+jonesy",
        r"which\s+games?\s+has\s+jonesy",
        r"which\s+games?\s+did\s+jonesy",
        r"what.*game.*most.*playtime",
        r"which.*game.*most.*episodes",
        r"what.*game.*longest.*complete",
        r"is\s+.+\s+recommended",  # Too broad - matches anywhere in message
        r"who\s+recommended\s+.+",   # Too broad - matches anywhere in message
        r"what.*recommend.*",  # Too broad - matches casual conversation
        r"jonesy.*gaming\s+(history|database|archive)",
    ]

    return any(re.search(pattern, content_lower) for pattern in game_query_patterns)

def test_recommendation_patterns_fixed(content: str) -> tuple:
    """Test the fixed recommendation patterns"""
    lower_content = content.lower()
    
    # Fixed recommendation patterns from message handler
    recommendation_patterns = [
        r"^is\s+(.+?)\s+recommended[\?\.]?$",  # Must be at start of message
        r"^has\s+(.+?)\s+been\s+recommended[\?\.]?$",  # Must be at start of message
        r"^who\s+recommended\s+(.+?)[\?\.]?$",  # Must be at start of message
        r"^what\s+(?:games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend\s+(.+?)[\?\.]?$"  # More specific pattern
    ]
    
    for pattern in recommendation_patterns:
        match = re.search(pattern, lower_content)
        if match:
            return True, match.group(1) if match.groups() else "matched"
    
    return False, None

def test_recommendation_patterns_old(content: str) -> tuple:
    """Test the old recommendation patterns that caused issues"""
    lower_content = content.lower()
    
    # Old overly broad patterns
    recommendation_patterns = [
        r"is\s+(.+?)\s+recommended[\?\.]?$",
        r"has\s+(.+?)\s+been\s+recommended[\?\.]?$",
        r"who\s+recommended\s+(.+?)[\?\.]?$",
        r"what.*recommend.*(.+?)[\?\.]?$"  # This was the problematic one
    ]
    
    for pattern in recommendation_patterns:
        match = re.search(pattern, lower_content)
        if match:
            return True, match.group(1) if match.groups() else "matched"
    
    return False, None

def run_tests():
    """Run comprehensive tests to verify the fixes"""
    print("🧪 Testing Ash Bot Monitoring Fixes")
    print("=" * 50)
    
    # Test cases - these should NOT trigger the bot (false positives from before)
    false_positive_cases = [
        "And the fact that Jam says, remember what games Jonesy likes to play. And then someone recommends Portal 1+2",
        "someone recommended Portal yesterday",
        "she said that we should try Portal",
        "I was telling someone about Portal recommendations",
        "we were discussing what games to recommend",
        "the fact that Portal is recommended",
        "remember when Portal was recommended",
        "Jam says remember what games Jonesy likes",
        "and then they mentioned Portal",
        "earlier someone suggested Halo"
    ]
    
    # Test cases - these SHOULD trigger the bot (legitimate queries)
    true_positive_cases = [
        "Has Jonesy played Portal?",
        "Did Jonesy play Portal 2?",
        "What games has Jonesy played?",
        "What game took longest to complete?",
        "Is Portal recommended?",
        "Who recommended Portal?",
        "What do you recommend?",
        "What games would you recommend?",
        "Should I recommend Halo?"
    ]
    
    print("\n🚫 Testing FALSE POSITIVE cases (should NOT trigger):")
    print("-" * 30)
    
    false_positive_count_old = 0
    false_positive_count_fixed = 0
    
    for i, case in enumerate(false_positive_cases, 1):
        old_result = detect_implicit_game_query_old(case)
        fixed_result = detect_implicit_game_query_fixed(case)
        
        old_rec_match, old_rec_extract = test_recommendation_patterns_old(case)
        fixed_rec_match, fixed_rec_extract = test_recommendation_patterns_fixed(case)
        
        if old_result:
            false_positive_count_old += 1
        if fixed_result:
            false_positive_count_fixed += 1
            
        status_old = "❌ TRIGGERED" if old_result else "✅ ignored"
        status_fixed = "❌ TRIGGERED" if fixed_result else "✅ ignored"
        
        print(f"{i:2d}. '{case[:50]}{'...' if len(case) > 50 else ''}'")
        print(f"    Old:   {status_old}")
        print(f"    Fixed: {status_fixed}")
        
        if old_rec_match:
            print(f"    Old Rec Pattern: ❌ MATCHED (extracted: '{old_rec_extract}')")
        if fixed_rec_match:
            print(f"    Fixed Rec Pattern: ❌ MATCHED (extracted: '{fixed_rec_extract}')")
        print()
    
    print("\n✅ Testing TRUE POSITIVE cases (should trigger):")
    print("-" * 30)
    
    true_positive_count_old = 0
    true_positive_count_fixed = 0
    
    for i, case in enumerate(true_positive_cases, 1):
        old_result = detect_implicit_game_query_old(case)
        fixed_result = detect_implicit_game_query_fixed(case)
        
        if old_result:
            true_positive_count_old += 1
        if fixed_result:
            true_positive_count_fixed += 1
            
        status_old = "✅ triggered" if old_result else "❌ IGNORED"
        status_fixed = "✅ triggered" if fixed_result else "❌ IGNORED"
        
        print(f"{i:2d}. '{case}'")
        print(f"    Old:   {status_old}")
        print(f"    Fixed: {status_fixed}")
        print()
    
    print("\n📊 SUMMARY:")
    print("=" * 30)
    print(f"False Positives (should be 0):")
    print(f"  Old version:   {false_positive_count_old}/{len(false_positive_cases)} ❌")
    print(f"  Fixed version: {false_positive_count_fixed}/{len(false_positive_cases)} {'✅' if false_positive_count_fixed == 0 else '❌'}")
    print()
    print(f"True Positives (should be {len(true_positive_cases)}):")
    print(f"  Old version:   {true_positive_count_old}/{len(true_positive_cases)} {'✅' if true_positive_count_old == len(true_positive_cases) else '❌'}")
    print(f"  Fixed version: {true_positive_count_fixed}/{len(true_positive_cases)} {'✅' if true_positive_count_fixed == len(true_positive_cases) else '❌'}")
    print()
    
    # Overall assessment
    old_score = (len(true_positive_cases) - false_positive_count_old + true_positive_count_old) / (len(false_positive_cases) + len(true_positive_cases)) * 100
    fixed_score = (len(true_positive_cases) - false_positive_count_fixed + true_positive_count_fixed) / (len(false_positive_cases) + len(true_positive_cases)) * 100
    
    print(f"Overall Accuracy:")
    print(f"  Old version:   {old_score:.1f}%")
    print(f"  Fixed version: {fixed_score:.1f}%")
    print()
    
    if false_positive_count_fixed == 0 and true_positive_count_fixed == len(true_positive_cases):
        print("🎉 SUCCESS: All fixes working correctly!")
        print("   • No false positives on casual conversation")
        print("   • All legitimate queries still detected")
    else:
        print("⚠️  Issues detected:")
        if false_positive_count_fixed > 0:
            print(f"   • {false_positive_count_fixed} false positives still occurring")
        if true_positive_count_fixed < len(true_positive_cases):
            print(f"   • {len(true_positive_cases) - true_positive_count_fixed} legitimate queries not detected")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    run_tests()
