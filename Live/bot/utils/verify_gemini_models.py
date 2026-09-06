"""
Tests which Gemini models are available and working with your API key using the Google GenAI SDK.
"""

import asyncio
import os
import sys


def get_api_key():
    """Get API key from environment or .env file"""
    import os

    # Try environment first
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
        return api_key
        
    # Manually read .env file if dotenv not available
    try:
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                for line in f:
                    if line.startswith('GEMINI_API_KEY='):
                        return line.strip().split('=', 1)[1]
    except Exception:
        pass
        
    return None

async def verify_models():
    """Verify Gemini SDK models"""
    print("🔍 ASH BOT - GEMINI SDK VERIFICATION")
    print("=" * 50)
    
    api_key = get_api_key()
    if not api_key:
        print("❌ ERROR: No GEMINI_API_KEY found in environment or .env file")
        return 1
        
    print("✅ API Key found")
    
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        print("✅ google.genai SDK initialized successfully")
        
        print("\n📋 Listing available models...")
        models = list(client.models.list())
        text_models = [m for m in models if m.name.startswith("models/gemini-2.5") or m.name.startswith("models/gemini-1.5")]
        
        for m in text_models:
            print(f"   • {m.name}")
            
        print(f"\n✅ Found {len(text_models)} relevant models.")
        
        print("\n🧪 Testing basic generation with gemini-2.5-flash...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Respond with "System Online"'
        )
        print(f"✅ Response received: {response.text.strip()}")
        print("\n✅ Verification complete. The new AI architecture is ready.")
        
    except ImportError:
        print("❌ ERROR: google-genai package not found. Run `pipenv install google-genai`")
        return 1
    except Exception as e:
        print(f"❌ ERROR during verification: {e}")
        return 1
        
    return 0

def main():
    return asyncio.run(verify_models())

if __name__ == "__main__":
    sys.exit(main())
