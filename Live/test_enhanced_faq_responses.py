#!/usr/bin/env python3
"""
Test script to verify enhanced FAQ responses for Jonesy disambiguation
"""

import os
import sys

# Add the current directory to the path
sys.path.append(os.path.dirname(__file__))

def test_enhanced_jonesy_faqs():
    """Test the enhanced Jonesy FAQ responses"""
    try:
        from bot.config import FAQ_RESPONSES
        
        print("🧪 Testing Enhanced Jonesy FAQ Responses...")
        print("=" * 60)
        
        # Test cases for new enhanced FAQs
        enhanced_faqs = [
            "who is jonesy",
            "tell me about jonesy", 
            "about jonesy",
            "jonesy info",
            "what about jonesy",
            "captain jonesy"
        ]
        
        results = []
        
        for faq in enhanced_faqs:
            if faq in FAQ_RESPONSES:
                response = FAQ_RESPONSES[faq]
                print(f"✅ **{faq.upper()}**")
                print(f"   Response: {response[:120]}...")
                print()
                
                # Check if it defaults to Captain Jonesy
                defaults_to_captain = any(phrase in response for phrase in [
                    "Captain Jonesy", "commanding officer", "server owner", 
                    "gaming content", "Discord server"
                ])
                
                # Check if it mentions the cat casually (optional)
                mentions_cat = any(phrase in response for phrase in [
                    "feline", "cat", "Nostromo", "ship's cat", "crew member"
                ])
                
                # Check for Ash-style language
                ash_style = any(phrase in response for phrase in [
                    "*[", "Analysis", "Mission", "Protocol", "Database", "Efficiency"
                ])
                
                analysis = {
                    'defaults_to_captain': defaults_to_captain,
                    'mentions_cat': mentions_cat,
                    'ash_style': ash_style
                }
                
                results.append((faq, analysis))
                
                status = "✅ GOOD" if defaults_to_captain and ash_style else "⚠️ NEEDS REVIEW"
                cat_status = "with cat reference" if mentions_cat else "no cat reference"
                
                print(f"   📊 Analysis: {status} ({cat_status})")
                print(f"      - Defaults to Captain: {'✅' if defaults_to_captain else '❌'}")
                print(f"      - Ash-style language: {'✅' if ash_style else '❌'}")
                print(f"      - Casual cat mention: {'✅' if mentions_cat else '➖'}")
                print()
            else:
                print(f"❌ **{faq.upper()}** - MISSING")
                results.append((faq, None))
                print()
        
        # Summary
        print("=" * 60)
        print("📋 ENHANCED FAQ SUMMARY:")
        
        good_responses = sum(1 for faq, analysis in results 
                           if analysis and analysis['defaults_to_captain'] and analysis['ash_style'])
        total_responses = len([r for r in results if r[1] is not None])
        
        print(f"   Total Enhanced FAQs: {total_responses}/{len(enhanced_faqs)}")
        print(f"   Quality Responses: {good_responses}/{total_responses}")
        
        with_cat_mentions = sum(1 for faq, analysis in results 
                              if analysis and analysis['mentions_cat'])
        print(f"   Include Cat References: {with_cat_mentions}/{total_responses}")
        
        success = good_responses == total_responses and total_responses == len(enhanced_faqs)
        
        print()
        if success:
            print("🎉 ALL ENHANCED FAQ TESTS PASSED!")
            print("   ✅ All responses default to Captain Jonesy")
            print("   ✅ All responses use Ash-style language")
            print(f"   ✅ {with_cat_mentions} responses include casual cat references")
            print("   ✅ Robust disambiguation system is working correctly")
        else:
            print("⚠️ Some enhanced FAQ tests need attention")
            
        return success
        
    except Exception as e:
        print(f"❌ Error testing enhanced FAQs: {e}")
        return False

def main():
    """Run enhanced FAQ tests"""
    print("🚀 Testing Enhanced Jonesy FAQ Responses")
    print("Testing new robust, hardcoded responses with Captain Jonesy defaults")
    print()
    
    success = test_enhanced_jonesy_faqs()
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
