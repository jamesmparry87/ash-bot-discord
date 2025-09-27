#!/usr/bin/env python3
"""
Direct HuggingFace API Test Script
Tests the exact API endpoint and configuration used by the Discord bot
"""

import os
import requests
import json
from datetime import datetime


def test_huggingface_api():
    """Test HuggingFace API directly with the same configuration as the bot"""
    print("🧪 Testing HuggingFace API Direct Connection")
    print("=" * 50)

    # Get API key from environment
    api_key = os.getenv('HUGGINGFACE_API_KEY')

    if not api_key:
        print("❌ HUGGINGFACE_API_KEY environment variable not found!")
        print("   Please set: export HUGGINGFACE_API_KEY='your_token_here'")
        return False

    print(f"✅ API Key found: {api_key[:10]}...{api_key[-10:] if len(api_key) > 20 else api_key}")
    print()

    # Test endpoint URL
    model_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
    print(f"🌐 Testing endpoint: {model_url}")

    # Setup headers (same as bot)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Test different prompt formats
    test_prompts = [
        {
            "name": "Current Bot Format",
            "inputs": "<s>[INST] Hello, can you respond to this test? [/INST]",
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.7,
                "return_full_text": False
            }
        },
        {
            "name": "Simple Instruction Format",
            "inputs": "[INST] Hello, can you respond to this test? [/INST]",
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.7,
                "return_full_text": False
            }
        },
        {
            "name": "Plain Text",
            "inputs": "Hello, can you respond to this test?",
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.7,
                "return_full_text": False
            }
        }
    ]

    success_count = 0

    for i, test_case in enumerate(test_prompts, 1):
        print(f"\n🔬 Test {i}: {test_case['name']}")
        print(f"   Prompt: {test_case['inputs'][:50]}...")

        try:
            response = requests.post(
                model_url,
                headers=headers,
                json=test_case,
                timeout=30
            )

            print(f"   Status Code: {response.status_code}")

            if response.status_code == 200:
                print("   ✅ SUCCESS!")
                try:
                    response_data = response.json()
                    if response_data and len(response_data) > 0:
                        generated_text = response_data[0].get("generated_text", "")
                        print(f"   Response: {generated_text[:100]}...")
                        success_count += 1
                    else:
                        print("   ⚠️ Empty response data")
                except json.JSONDecodeError:
                    print(f"   ⚠️ Non-JSON response: {response.text[:100]}...")

            elif response.status_code == 404:
                print("   ❌ 404 NOT FOUND")
                print(f"   Error: {response.text}")

            elif response.status_code == 401:
                print("   ❌ 401 UNAUTHORIZED")
                print("   Issue: API token may be invalid or expired")
                print(f"   Error: {response.text}")

            elif response.status_code == 403:
                print("   ❌ 403 FORBIDDEN")
                print("   Issue: Token may not have access to this model")
                print(f"   Error: {response.text}")

            elif response.status_code == 429:
                print("   ❌ 429 RATE LIMITED")
                print(f"   Error: {response.text}")

            elif response.status_code >= 500:
                print(f"   ❌ {response.status_code} SERVER ERROR")
                print("   Issue: HuggingFace server problem")
                print(f"   Error: {response.text}")

            else:
                print(f"   ❌ Unexpected status: {response.status_code}")
                print(f"   Response: {response.text}")

        except requests.exceptions.Timeout:
            print("   ❌ TIMEOUT - Request took too long")
        except requests.exceptions.ConnectionError:
            print("   ❌ CONNECTION ERROR - Cannot reach HuggingFace API")
        except Exception as e:
            print(f"   ❌ UNEXPECTED ERROR: {e}")

    print("\n" + "=" * 50)
    print("📊 Test Summary:")
    print(f"   Successful requests: {success_count}/{len(test_prompts)}")

    if success_count > 0:
        print("   ✅ API is working! The bot configuration needs adjustment.")
        return True
    else:
        print("   ❌ All tests failed. Check API key and model availability.")
        return False


if __name__ == "__main__":
    success = test_huggingface_api()

    if not success:
        print("\n🔧 Troubleshooting Tips:")
        print("1. Verify your HuggingFace token has access to the model")
        print("2. Check if the model requires additional permissions")
        print("3. Try a different model that's publicly available")
        print("4. Ensure your token hasn't expired")
