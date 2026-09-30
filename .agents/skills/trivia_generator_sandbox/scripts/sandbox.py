import argparse
import asyncio
import json
import os
import sys

# Add the Live directory to the path so we can import bot modules
LIVE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Live")
sys.path.insert(0, os.path.abspath(LIVE_DIR))

def load_env():
    env_path = os.path.join(LIVE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

async def run_sandbox(category=None):
    load_env()
    
    from bot.handlers.trivia.generator import generate_ai_trivia_question
    
    print(f"🎮 TRIVIA SANDBOX: Starting generation offline test...")
    if category:
        print(f"🎯 Forcing category: {category}")
        
    questions = await generate_ai_trivia_question(force_category=category)
    
    if not questions:
        print("❌ Failed to generate questions.")
        return
        
    print(f"\n✅ Generated {len(questions)} questions successfully!\n")
    print("="*60)
    for i, q in enumerate(questions):
        print(f"QUESTION {i+1}: {q.get('question_text')}")
        print(f"TYPE: {q.get('question_type')}")
        print(f"CORRECT ANSWER: {q.get('correct_answer')}")
        if q.get('question_type') == 'multiple_choice':
            print(f"DECOYS: {q.get('decoy_1')}, {q.get('decoy_2')}, {q.get('decoy_3')}")
            
        dq = q.get('dynamic_query_type')
        if dq:
            print(f"DYNAMIC QUERY (JSON):")
            if isinstance(dq, str):
                try:
                    dq_dict = json.loads(dq)
                    print(json.dumps(dq_dict, indent=2))
                except json.JSONDecodeError:
                    print(dq)
            else:
                print(json.dumps(dq, indent=2))
        print("="*60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trivia Generator Sandbox")
    parser.add_argument("--category", type=str, help="Force a specific trivia category (e.g. Clip_Vibe_Check)")
    args = parser.parse_args()
    
    # Ensure Windows console can print emojis
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
        
    asyncio.run(run_sandbox(category=args.category))
