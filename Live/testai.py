import asyncio
import os

# Try to import google.generativeai
try:
    import google.generativeai as genai  # type: ignore

    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False


async def test_ai_simple():
    """Test AI with a simple game query"""
    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")

    if not GEMINI_API_KEY or not GENAI_AVAILABLE or genai is None:
        print("❌ AI not available")
        return

    try:
        genai.configure(api_key=GEMINI_API_KEY)  # type: ignore
        model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore

        prompt = """What is the genre, series name, release year, and common alternative names for the video game "Batman: Arkham Origins"?

Respond in this exact JSON format:
{
  "Batman: Arkham Origins": {
    "genre": "Action-Adventure",
    "series_name": "Batman: Arkham", 
    "release_year": 2013,
    "alternative_names": ["Arkham Origins", "Batman AO"]
  }
}

Only respond with valid JSON."""

        print("🧪 Testing AI with Batman: Arkham Origins...")
        print(f"📝 Prompt: {prompt}")

        response = model.generate_content(prompt)

        if response and hasattr(response, "text") and response.text:
            response_text = response.text.strip()
            print(f"🤖 Raw Response: {response_text}")

            # Clean response
            clean_text = response_text
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            print(f"🧹 Cleaned Response: {clean_text}")

            # Try to parse JSON
            import json

            try:
                parsed_data = json.loads(clean_text)
                print(f"✅ JSON Parsing Successful: {parsed_data}")

                if "Batman: Arkham Origins" in parsed_data:
                    game_data = parsed_data["Batman: Arkham Origins"]
                    print(f"✅ Game Data Found:")
                    print(f"  • Genre: {game_data.get('genre')}")
                    print(f"  • Series: {game_data.get('series_name')}")
                    print(f"  • Year: {game_data.get('release_year')}")
                    print(f"  • Alt Names: {game_data.get('alternative_names')}")
                else:
                    print(f"⚠️ Game not found in response keys: {list(parsed_data.keys())}")

            except json.JSONDecodeError as e:
                print(f"❌ JSON Parsing Failed: {e}")
        else:
            print("❌ No response from AI")

    except Exception as e:
        print(f"❌ AI Test Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_ai_simple())
