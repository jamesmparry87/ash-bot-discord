#!/usr/bin/env python3
"""
Simple test to verify Mixtral-8x7B-Instruct-v0.1 fix for HuggingFace 404 errors
"""

import os
import requests

def test_mixtral_fix():
    """Test the specific Mixtral model fix"""
    print("🧪 Testing Mixtral-8x7B-Instruct-v0.1 Fix")
    print("=" * 50)
    
    # Get API key
    api_key = os.getenv('HUGGINGFACE_API_KEY')
    if not api_key:
        print("❌ HUGGINGFACE_API_KEY not found")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    
    # Test the specific model we updated the bot to use
    model_url = "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": "<s>[INST] Hello, this is a test [/INST]",
        "parameters": {
            "max_new_tokens": 50,
            "temperature": 0.7,
            "return_full_text": False
        }
    }
    
    print(f"\n🌐 Testing: {model_url}")
    
    try:
        response = requests.post(model_url, headers=headers, json=payload, timeout=30)
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ SUCCESS - Model is accessible!")
            try:
                data = response.json()
                if data and len(data) > 0:
                    text = data[0].get("generated_text", "").strip()
                    print(f"🤖 Response: {text[:100]}...")
                    return True
                else:
                    print("⚠️ Empty response data")
            except Exception as e:
                print(f"⚠️ JSON parsing error: {e}")
                
        elif response.status_code == 404:
            print("❌ 404 NOT FOUND - Model not accessible via Inference API")
            print("   This model may require Pro subscription or different access")
            
        elif response.status_code == 401:
            print("❌ 401 UNAUTHORIZED - Token issue")
            
        elif response.status_code == 403:
            print("❌ 403 FORBIDDEN - No access to this model")
            
        else:
            print(f"❌ Unexpected status: {response.status_code}")
            
        print(f"📝 Error details: {response.text[:200]}...")
        return False
        
    except Exception as e:
        print(f"❌ Request error: {e}")
        return False

if __name__ == "__main__":
    success = test_mixtral_fix()
    print(f"\n{'✅ Test passed' if success else '❌ Test failed'}")
    
    if not success:
        print("\n💡 Alternative solutions:")
        print("   1. HuggingFace may require Pro subscription for this model")
        print("   2. The model might not be available via Inference API")
        print("   3. Consider using the bot with Gemini primary AI only")
        print("   4. The 404 errors may be resolved by graceful error handling we added")
