"""
Gemini Model Testing Utility

Tests which Gemini models are available and working with your API key.
Useful for debugging quota issues and checking model availability.

Usage:
    python -m bot.utils.test_gemini_models
    or
    from bot.utils.test_gemini_models import test_all_models
    results = await test_all_models()
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

# Load environment variables from .env file
try:
    from pathlib import Path

    # Find .env file in Live directory
    env_path = Path(__file__).parent.parent.parent / '.env'
    
    if env_path.exists():
        # Manually read .env file if dotenv not available
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    os.environ[key.strip()] = value
        print(f"🔧 Loaded .env from: {env_path}")
    else:
        print(f"⚠️ .env file not found at: {env_path}")
except Exception as e:
    print(f"⚠️ Could not load .env file: {e}")

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("❌ google.generativeai not installed. Run: pip install google-generativeai")
    sys.exit(1)


# Models to test (in priority order)
GEMINI_MODELS_TO_TEST = [
    'gemini-2.0-flash',      # Latest, fastest (may require paid tier)
    'gemini-1.5-flash',      # Fast, reliable free tier
    'gemini-1.5-pro',        # More capable, slower
    'gemini-1.0-pro',        # Legacy fallback
]


def configure_api():
    """Configure Gemini API with API key from environment"""
    api_key = os.getenv('GOOGLE_API_KEY')
    
    if not api_key:
        print("❌ GOOGLE_API_KEY not found in environment variables")
        print("   Set it with: export GOOGLE_API_KEY='your-key-here'")
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    print(f"✅ API configured with key: {api_key[:10]}...{api_key[-4:]}")


def list_available_models():
    """List all models available from Gemini API"""
    try:
        print("\n📋 Listing all available Gemini models from API...")
        models = genai.list_models()
        
        gemini_models = [m for m in models if 'gemini' in m.name.lower()]
        
        if not gemini_models:
            print("⚠️ No Gemini models found in API response")
            return []
        
        print(f"✅ Found {len(gemini_models)} Gemini models in API catalog:")
        for model in gemini_models:
            print(f"   • {model.name}")
            print(f"     Display: {model.display_name}")
            if hasattr(model, 'supported_generation_methods'):
                print(f"     Methods: {model.supported_generation_methods}")
        
        return [m.name for m in gemini_models]
        
    except Exception as e:
        print(f"❌ Error listing models: {e}")
        return []


def test_model(model_name: str) -> Dict[str, any]:
    """Test if a specific model works with current API key"""
    result = {
        'model': model_name,
        'available': False,
        'error': None,
        'response_time': None,
        'response_text': None
    }
    
    try:
        start_time = datetime.now()
        
        # Create model instance
        model = genai.GenerativeModel(model_name)
        
        # Test with minimal request
        response = model.generate_content(
            "Test", 
            generation_config={"max_output_tokens": 5}
        )
        
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds()
        
        if response and response.text:
            result['available'] = True
            result['response_time'] = response_time
            result['response_text'] = response.text[:50]
            print(f"✅ {model_name:25s} - WORKS ({response_time:.2f}s) - Response: '{response.text[:30]}'")
        else:
            result['error'] = "Empty response"
            print(f"⚠️ {model_name:25s} - Empty response returned")
            
    except Exception as e:
        error_str = str(e)
        result['error'] = error_str
        
        # Categorize error type
        if "quota" in error_str.lower() or "429" in error_str:
            if "limit: 0" in error_str or "limit:0" in error_str:
                print(f"❌ {model_name:25s} - NOT AVAILABLE ON YOUR TIER (quota limit: 0)")
            else:
                print(f"❌ {model_name:25s} - QUOTA EXHAUSTED (daily/minute limit reached)")
        elif "not found" in error_str.lower() or "404" in error_str:
            print(f"⚠️ {model_name:25s} - MODEL NOT FOUND")
        elif "permission" in error_str.lower() or "403" in error_str:
            print(f"❌ {model_name:25s} - PERMISSION DENIED (check API key)")
        else:
            print(f"❌ {model_name:25s} - ERROR: {error_str[:80]}")
    
    return result


def test_all_models() -> Dict[str, List[Dict]]:
    """Test all Gemini models and return results"""
    print(f"\n{'='*80}")
    print("🔍 TESTING GEMINI MODELS")
    print(f"{'='*80}")
    print(f"⏰ Time: {datetime.now(ZoneInfo('Europe/London')).strftime('%Y-%m-%d %H:%M:%S UK')}")
    
    results = {
        'working': [],
        'quota_issues': [],
        'not_available': [],
        'errors': []
    }
    
    for model_name in GEMINI_MODELS_TO_TEST:
        result = test_model(model_name)
        
        if result['available']:
            results['working'].append(result)
        elif result['error']:
            error_lower = result['error'].lower()
            if "quota" in error_lower or "429" in error_lower:
                if "limit: 0" in error_lower or "limit:0" in error_lower:
                    results['not_available'].append(result)
                else:
                    results['quota_issues'].append(result)
            elif "not found" in error_lower or "404" in error_lower:
                results['not_available'].append(result)
            else:
                results['errors'].append(result)
    
    return results


def print_summary(results: Dict[str, List[Dict]]):
    """Print summary of test results"""
    print(f"\n{'='*80}")
    print("📊 SUMMARY")
    print(f"{'='*80}")
    
    if results['working']:
        print(f"\n✅ WORKING MODELS ({len(results['working'])} available):")
        for r in results['working']:
            print(f"   • {r['model']} (response time: {r['response_time']:.2f}s)")
        
        print("\n💡 RECOMMENDATION:")
        primary = results['working'][0]['model']
        print(f"   Use '{primary}' as primary model in ai_handler.py")
        
        if len(results['working']) > 1:
            fallbacks = [r['model'] for r in results['working'][1:]]
            print(f"   Available fallbacks: {', '.join(fallbacks)}")
    else:
        print("\n❌ NO WORKING MODELS FOUND")
        print("   This means AI features will not work with current API key/configuration")
    
    if results['not_available']:
        print(f"\n⚠️ NOT AVAILABLE ON YOUR TIER ({len(results['not_available'])} models):")
        for r in results['not_available']:
            print(f"   • {r['model']} - May require paid plan or regional availability")
    
    if results['quota_issues']:
        print(f"\n🚫 QUOTA EXHAUSTED ({len(results['quota_issues'])} models):")
        for r in results['quota_issues']:
            print(f"   • {r['model']} - Daily/minute limit reached")
        print("   💡 Quotas reset at 8:00 AM UK time (Google's reset time)")
    
    if results['errors']:
        print(f"\n❌ OTHER ERRORS ({len(results['errors'])} models):")
        for r in results['errors']:
            print(f"   • {r['model']} - {r['error'][:100]}")
    
    print(f"\n{'='*80}")


def main():
    """Main entry point for CLI usage"""
    print(f"\n{'#'*80}")
    print("# GEMINI MODEL TESTING UTILITY")
    print("# Tests which Gemini models work with your API key")
    print(f"{'#'*80}\n")
    
    # Configure API
    configure_api()
    
    # List available models from API
    api_models = list_available_models()
    
    # Test each model
    results = test_all_models()
    
    # Print summary
    print_summary(results)
    
    # Return exit code based on results
    if results['working']:
        print("\n✅ SUCCESS: At least one working model found")
        return 0
    else:
        print("\n❌ FAILURE: No working models found")
        return 1


if __name__ == "__main__":
    sys.exit(main())
