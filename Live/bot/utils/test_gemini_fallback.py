from bot.handlers import ai_handler
from bot.config import GEMINI_MODEL_CASCADE
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


async def run_test():
    print("🚀 Starting Gemini Model Fallback / Cascade Logic Test\n")

    # 1. Identify models
    print(f"📋 Configured Fallback Chain ({len(GEMINI_MODEL_CASCADE)} models):")
    for i, model in enumerate(GEMINI_MODEL_CASCADE):
        role = "Primary" if i == 0 else f"Fallback {i}"
        print(f"   {i+1}. {model} ({role})")

    print("\n--- Initializing AI Handler Environment ---")
    ai_handler.ai_enabled = True
    ai_handler.primary_ai = "gemini"
    ai_handler.working_gemini_models = GEMINI_MODEL_CASCADE.copy()
    ai_handler.current_gemini_model = GEMINI_MODEL_CASCADE[0]

    # Mock the gemini_client
    class MockGenerateContentResponse:
        def __init__(self, text):
            self.text = text

    class MockModels:
        def __init__(self):
            self.call_count = 0

        def generate_content(self, *args, **kwargs):
            self.call_count += 1
            model_used = kwargs.get('model')
            print(f"\n📡 API Call #{self.call_count} intercepted! Targeting model: {model_used}")

            # Simulate 429 quota exhaustion on the first call (Primary model)
            if self.call_count == 1:
                print(f"   ❌ Injecting simulated HTTP 429 RESOURCE_EXHAUSTED error for {model_used}...")
                raise Exception("429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerProjectPerModel-FreeTier")

            # Succeed on the second call (Fallback model)
            print(f"   ✅ Returning successful response for fallback model {model_used}...")
            return MockGenerateContentResponse(f"Success! I am responding using {model_used}.")

    mock_client = MagicMock()
    mock_client.models = MockModels()
    ai_handler.gemini_client = mock_client

    # Run the test by calling the actual rate-limiting function
    print("\n--- Executing Test Call ---")
    prompt = "Hello, please answer this test prompt."
    print(f"User Prompt: '{prompt}'")

    try:
        response, status = await ai_handler.call_ai_with_rate_limiting(
            prompt=prompt,
            user_id=123456789,
            context="test_cascade"
        )

        print("\n--- Summary Report ---")
        print("1. Was the 429 error caught properly? YES")
        print(f"2. Current Active Model after execution: {ai_handler.current_gemini_model}")
        print(f"3. Final Status returned by handler: {status}")
        print(f"4. Output from Fallback Model:\n   '{response}'\n")

        if ai_handler.current_gemini_model == GEMINI_MODEL_CASCADE[1] and status == "success":
            print("🎉 VERIFICATION PASSED: Cascade immediately retried using the next model in the chain without crashing!")
        else:
            print("❌ VERIFICATION FAILED: Cascade did not behave as expected.")

    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: System crashed with an unhandled exception: {e}")

if __name__ == "__main__":
    # Workaround for Windows asyncio loop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_test())
