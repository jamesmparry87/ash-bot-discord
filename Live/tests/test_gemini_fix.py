"""
Quick test to verify Gemini API key configuration works
"""
import os

# Check API key (should be set in environment)
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
print(f"API Key present: {bool(GEMINI_API_KEY)}")
if GEMINI_API_KEY:
    print(f"API Key length: {len(GEMINI_API_KEY)}")
    print(f"API Key starts with: {GEMINI_API_KEY[:10]}...")
else:
    print("❌ GOOGLE_API_KEY not found in environment!")
    print("Set it with: $env:GOOGLE_API_KEY='your-key-here' (PowerShell)")
    exit(1)

# Try importing the new SDK
try:
    from google import genai
    print("✅ google-genai module imported successfully")

    # Try creating a model with the API key
    print(f"\nTesting model creation with api_key parameter...")
    test_model = genai.GenerativeModel(
        model_name="gemini-2.0-flash-001",
        api_key=GEMINI_API_KEY
    )
    print("✅ Model created successfully with api_key parameter")

    # Try a simple generation
    print("\nTesting actual API call...")
    response = test_model.generate_content(
        "Say 'test successful' in 2 words",
        generation_config={"max_output_tokens": 10}
    )

    if response and hasattr(response, 'text') and response.text:
        print(f"✅ Test generation successful: {response.text}")
        print("\n🎉 ALL TESTS PASSED - Gemini API is working correctly!")
    else:
        print("❌ Test generation returned empty response")
        print(f"Response object: {response}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure google-genai is installed: pip install google-genai")
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
