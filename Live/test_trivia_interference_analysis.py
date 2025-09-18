#!/usr/bin/env python3
"""
Analysis of trivia response interference from gaming query patterns
"""

import re
from typing import Match, Optional, Tuple

def route_query(content: str) -> Tuple[str, Optional[Match[str]]]:
    """Copy of the route_query function from message_handler.py for testing"""
    lower_content = content.lower()

    # Define query patterns and their types - COPIED FROM message_handler.py
    query_patterns = {
        "statistical": [
            r"what\s+game\s+series\s+.*most\s+minutes",
            r"what\s+game\s+series\s+.*most\s+playtime",
            r"what\s+game\s+.*highest\s+average.*per\s+episode",
            r"what\s+game\s+.*longest.*per\s+episode",
            r"what\s+game\s+.*took.*longest.*complete",
            r"which\s+game\s+.*most\s+episodes",
            r"which\s+game\s+.*longest.*complete",
            r"what.*game.*most.*playtime",
            r"which.*series.*most.*playtime",
            r"what.*game.*shortest.*episodes",
            r"which.*game.*fastest.*complete",
            r"what.*game.*most.*time",
            r"which.*game.*took.*most.*time",
            # Additional patterns for playtime queries that were falling through to AI
            r"what\s+is\s+the\s+longest\s+game.*jonesy.*played",
            r"which\s+is\s+the\s+longest\s+game.*jonesy.*played", 
            r"what\s+game\s+took.*longest.*for\s+jonesy",
            r"what\s+game\s+has\s+the\s+most\s+playtime",
            r"what\s+game\s+has\s+the\s+longest\s+playtime",
            r"which\s+game\s+has\s+the\s+most\s+hours",
            r"what.*longest.*game.*jonesy.*played",
            r"what.*game.*longest.*playtime",
            r"which.*game.*longest.*hours",
            r"what.*game.*most.*hours"
        ],
        "genre": [
            r"what\s+(.*?)\s+games\s+has\s+jonesy\s+played",
            r"what\s+(.*?)\s+games\s+did\s+jonesy\s+play",
            r"has\s+jonesy\s+played\s+any\s+(.*?)\s+games",
            r"did\s+jonesy\s+play\s+any\s+(.*?)\s+games",
            r"list\s+(.*?)\s+games\s+jonesy\s+played",
            r"show\s+me\s+(.*?)\s+games\s+jonesy\s+played"
        ],
        "year": [
            r"what\s+games\s+from\s+(\d{4})\s+has\s+jonesy\s+played",
            r"what\s+games\s+from\s+(\d{4})\s+did\s+jonesy\s+play",
            r"has\s+jonesy\s+played\s+any\s+games\s+from\s+(\d{4})",
            r"did\s+jonesy\s+play\s+any\s+games\s+from\s+(\d{4})",
            r"list\s+(\d{4})\s+games\s+jonesy\s+played"
        ],
        "game_status": [
            r"has\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+captain\s+jonesy\s+played\s+(.+?)[\?\.]?$",
            r"did\s+captain\s+jonesy\s+play\s+(.+?)[\?\.]?$",
            r"has\s+jonesyspacecat\s+played\s+(.+?)[\?\.]?$",
            r"did\s+jonesyspacecat\s+play\s+(.+?)[\?\.]?$"
        ],
        "game_details": [
            r"how long did jonesy play (.+?)[\?\.]?$",
            r"how many hours did jonesy play (.+?)[\?\.]?$",
            r"what's the playtime for (.+?)[\?\.]?$",
            r"what is the playtime for (.+?)[\?\.]?$",
            r"how much time did jonesy spend on (.+?)[\?\.]?$",
            r"how long did (.+?) take jonesy[\?\.]?$",
            r"how long did (.+?) take to complete[\?\.]?$",
            r"what's the total time for (.+?)[\?\.]?$"
        ],
        "recommendation": [
            r"^is\s+(.+?)\s+recommended[\?\.]?$",  # Must be at start of message
            r"^has\s+(.+?)\s+been\s+recommended[\?\.]?$",  # Must be at start of message
            r"^who\s+recommended\s+(.+?)[\?\.]?$",  # Must be at start of message
            r"^what\s+(?:games?\s+)?(?:do\s+you\s+|would\s+you\s+|should\s+i\s+)?recommend\s+(.+?)[\?\.]?$"  # More specific pattern
        ],
        "youtube_views": [
            r"what\s+game\s+has\s+gotten.*most\s+views",
            r"which\s+game\s+has\s+the\s+most\s+views",
            r"what\s+game\s+has\s+the\s+highest\s+views",
            r"what.*game.*most.*views",
            r"which.*game.*most.*views",
            r"what.*game.*highest.*views",
            r"most\s+viewed\s+game",
            r"highest\s+viewed\s+game",
            r"what\s+game\s+got.*most\s+views",
            r"which\s+game\s+got.*most\s+views"
        ]
    }

    # Check each query type
    for query_type, patterns in query_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, lower_content)
            if match:
                return query_type, match

    return "unknown", None

def test_trivia_answer_interference():
    """Test if typical trivia answers get incorrectly matched by gaming query patterns"""
    print("🔍 Trivia Answer Interference Analysis")
    print("=" * 50)
    
    # Common trivia answers that might get falsely matched
    trivia_answers = [
        "God of War",
        "Final Fantasy VII",
        "The Witcher 3",
        "Dark Souls",
        "Mass Effect",
        "Cyberpunk 2077",
        "Red Dead Redemption",
        "The Last of Us",
        "Horizon Zero Dawn",
        "Ghost of Tsushima",
        "A",  # Multiple choice
        "B",  # Multiple choice
        "C",  # Multiple choice
        "D",  # Multiple choice
        "42",  # Numeric answer
        "2018",  # Year answer
        "Action",  # Genre answer
        "RPG",  # Genre answer
        "Horror",  # Genre answer
    ]
    
    print(f"\n📝 Testing {len(trivia_answers)} common trivia answers...")
    
    false_positives = []
    
    for answer in trivia_answers:
        query_type, match = route_query(answer)
        if query_type != "unknown":
            false_positives.append({
                "answer": answer,
                "matched_type": query_type,
                "matched_pattern": match.pattern if match else "unknown"
            })
            print(f"❌ FALSE POSITIVE: '{answer}' matched as '{query_type}' query")
        else:
            print(f"✅ '{answer}' - no false match")
    
    print(f"\n📊 Results:")
    print(f"   Total answers tested: {len(trivia_answers)}")
    print(f"   False positives: {len(false_positives)}")
    print(f"   Accuracy: {((len(trivia_answers) - len(false_positives)) / len(trivia_answers)) * 100:.1f}%")
    
    if false_positives:
        print(f"\n⚠️ PROBLEMATIC PATTERNS:")
        for fp in false_positives:
            print(f"   • '{fp['answer']}' → {fp['matched_type']} (pattern: {fp.get('matched_pattern', 'unknown')})")
    
    return len(false_positives) == 0

def test_legitimate_gaming_queries():
    """Test that legitimate gaming queries still work correctly"""
    print(f"\n🎮 Testing Legitimate Gaming Queries")
    print("=" * 40)
    
    legitimate_queries = [
        ("Has Jonesy played God of War?", "game_status"),
        ("What horror games has Jonesy played?", "genre"),
        ("What game has the most playtime?", "statistical"),
        ("How long did Jonesy play Mass Effect?", "game_details"),
        ("What games from 2018 has Jonesy played?", "year"),
        ("Is Cyberpunk recommended?", "recommendation"),
        ("What game has the most views?", "youtube_views"),
    ]
    
    all_correct = True
    for query, expected_type in legitimate_queries:
        query_type, match = route_query(query)
        if query_type == expected_type:
            print(f"✅ '{query}' → {query_type}")
        else:
            print(f"❌ '{query}' → {query_type} (expected: {expected_type})")
            all_correct = False
    
    return all_correct

def analyze_problematic_patterns():
    """Analyze which patterns are too broad and causing false positives"""
    print(f"\n🔍 Pattern Analysis")
    print("=" * 25)
    
    # Most problematic patterns identified
    problematic_patterns = [
        # These patterns are too broad and match simple game names
        (r"has\s+jonesy\s+played\s+(.+?)[\?\.]?$", "game_status", "Matches any text after 'has jonesy played'"),
        (r"did\s+jonesy\s+play\s+(.+?)[\?\.]?$", "game_status", "Matches any text after 'did jonesy play'"),
        (r"what.*game.*most.*playtime", "statistical", "Too broad - matches isolated words"),
        (r"what.*longest.*game.*jonesy.*played", "statistical", "Too broad - matches isolated words"),
    ]
    
    print("🚨 IDENTIFIED PROBLEMATIC PATTERNS:")
    for pattern, query_type, issue in problematic_patterns:
        print(f"   • {query_type}: {pattern}")
        print(f"     Issue: {issue}")
        print()
    
    return problematic_patterns

def recommend_solutions():
    """Recommend solutions to fix the interference"""
    print("💡 RECOMMENDED SOLUTIONS:")
    print("=" * 30)
    
    solutions = [
        "1. Make gaming query patterns more specific",
        "   - Require question words (what, which, how, etc.)",
        "   - Require question punctuation (?) for most patterns",
        "   - Add word boundaries to prevent partial matches",
        "",
        "2. Add trivia session awareness to gaming handler",
        "   - Check for active trivia session before processing",
        "   - Skip gaming queries if trivia is active",
        "",
        "3. Improve pattern specificity",
        "   - 'has jonesy played X?' → require question mark",
        "   - Statistical patterns → require complete question structure",
        "   - Add minimum word count requirements",
        "",
        "4. Add trivia context detection",
        "   - Check if message is a short answer (1-3 words)",
        "   - Skip gaming processing for likely trivia answers"
    ]
    
    for solution in solutions:
        print(solution)

def main():
    """Run the trivia interference analysis"""
    print("🧪 Trivia Response Interference Analysis")
    print("=" * 60)
    
    # Test for false positives
    no_false_positives = test_trivia_answer_interference()
    
    # Test legitimate queries still work
    legitimate_queries_work = test_legitimate_gaming_queries()
    
    # Analyze problematic patterns
    problematic_patterns = analyze_problematic_patterns()
    
    # Provide solutions
    recommend_solutions()
    
    print("\n" + "=" * 60)
    print("📊 ANALYSIS SUMMARY:")
    print(f"   • False positives detected: {'No' if no_false_positives else 'Yes'}")
    print(f"   • Legitimate queries work: {'Yes' if legitimate_queries_work else 'No'}")
    print(f"   • Problematic patterns found: {len(problematic_patterns)}")
    
    if not no_false_positives:
        print(f"\n⚠️ CONCLUSION: Gaming query patterns are too broad and will")
        print(f"   interfere with trivia answers. Patterns need to be made more specific.")
    else:
        print(f"\n✅ CONCLUSION: No interference detected from gaming query patterns.")

if __name__ == "__main__":
    main()
