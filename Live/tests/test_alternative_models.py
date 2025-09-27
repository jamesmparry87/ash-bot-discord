#!/usr/bin/env python3
"""
Test alternative HuggingFace models that are publicly available via Inference API
"""

import os
import requests
import json


def test_alternative_models():
    """Test publicly available models via HuggingFace Inference API"""
    print("🧪 Testing Alternative HuggingFace Models")
    print("=" * 50)

    api_key = os.getenv('HUGGINGFACE_API_KEY')
    if not api_key:
        print("❌ HUGGINGFACE_API_KEY not found!")
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Test publicly available models
    test_models = [
        {
            "name": "Microsoft DialoGPT Medium",
            "model": "microsoft/DialoGPT-medium",
            "prompt": "Hello, how are you?"
        },
        {
            "name": "Facebook BlenderBot Small",
            "model": "facebook/blenderbot_small-90M",
            "prompt": "Hello, can you help me?"
        },
        {
            "name": "GPT-2 Small",
            "model": "gpt2",
            "prompt": "Hello, this is a test of"
        },
        {
            "name": "DistilGPT-2",
            "model": "distilgpt2",
            "prompt": "The weather today is"
        }
    ]

    successful_models = []

    for model_info in test_models:
        print(f"\n🔬 Testing: {model_info['name']}")
        print(f"   Model: {model_info['model']}")

        url = f"https://api-inference.huggingface.co/models/{model_info['model']}"
        payload = {
            "inputs": model_info['prompt'],
            "parameters": {
                "max_new_tokens": 50,
                "temperature": 0.7,
                "return_full_text": False
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        text = data[0].get("generated_text", "")
                        print(f"   ✅ SUCCESS: {text[:60]}...")
                        successful_models.append(model_info)
                    else:
                        print(f"   ⚠️ Unexpected response format: {data}")
                except json.JSONDecodeError:
                    print(f"   ⚠️ Non-JSON response: {response.text[:60]}...")
            else:
                print(f"   ❌ Error: {response.text[:100]}")

        except Exception as e:
            print(f"   ❌ Exception: {e}")

    print(f"\n" + "=" * 50)
    print(f"📊 Results: {len(successful_models)}/{len(test_models)} models working")

    if successful_models:
        print("\n✅ Working Models for Bot Integration:")
        for model in successful_models:
            print(f"   • {model['name']}: {model['model']}")
        return True
    else:
        print("\n❌ No models working - check API permissions")
        return False


if __name__ == "__main__":
    success = test_alternative_models()

    if success:
        print(f"\n🎯 Recommendation:")
        print(f"   Update your bot to use one of the working models above")
        print(f"   Replace 'mistralai/Mistral-7B-Instruct-v0.3' in:")
        print(f"   - Live/bot/handlers/ai_handler.py (line ~540 and ~720)")
    else:
        print(f"\n🔧 Next Steps:")
        print(f"   1. Check HuggingFace account permissions")
        print(f"   2. Verify token has inference API access")
        print(f"   3. Consider using a different AI service")
