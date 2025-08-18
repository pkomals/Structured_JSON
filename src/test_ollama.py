# test_ollama.py
import ollama
import json

def test_ollama():
    print("🔍 Testing Ollama connection...")
    
    try:
        # Test basic connection
        models = ollama.list()
        print(f"✅ Connected to Ollama!")
        print(f"📋 Raw response: {models}")
        print(f"📋 Response type: {type(models)}")
        
        # Try to extract model names
        if isinstance(models, dict):
            if 'models' in models:
                model_names = [m.get('name', 'unknown') for m in models['models']]
                print(f"🎯 Model names: {model_names}")
            else:
                print(f"🔧 Dict keys: {list(models.keys())}")
        
        # Test a simple chat
        print("\n🧪 Testing chat with gemma:2b...")
        response = ollama.chat(
            model='gemma:2b',
            messages=[{'role': 'user', 'content': 'Say "Hello" in JSON format like {"message": "Hello"}'}]
        )
        
        print(f"💬 Chat response: {response}")
        print(f"💬 Message content: {response.get('message', {}).get('content', 'No content')}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ollama()