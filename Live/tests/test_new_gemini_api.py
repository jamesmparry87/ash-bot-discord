"""
Test script for the NEW google-genai v1.56+ API
This shows the correct way to use the new Client-based API
"""
import os
from google import genai

# Get API key from environment
API_KEY = os.getenv('GOOGLE_API_KEY')

if not API_KEY:
    print("❌ GOOGLE_API_KEY not set!")
    exit(1)

# Create client (NEW API)
client = genai.Client(api_key=API_KEY)

print("✅ Client created successfully")
print(f"Client type: {type(client)}")
print(f"Client has models: {hasattr(client, 'models')}")

# Test model
model_name = 'gemini-2.0-flash-exp'

try:
    # NEW API: client.models.generate_content()
    response = client.models.generate_content(
        model=model_name,
        contents="Say hello in one sentence",
        config={"max_output_tokens": 50}
    )

    print(f"\n✅ SUCCESS!")
    print(f"Response type: {type(response)}")
    print(f"Has text: {hasattr(response, 'text')}")
    if hasattr(response, 'text'):
        print(f"Response text: {response.text}")
    else:
        print(f"Response object: {response}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
