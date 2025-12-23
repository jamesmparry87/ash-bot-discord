import google.generativeai as genai

# Configure the API with your key

genai.configure(api_key="AIzaSyBTc4adXAEzSTX6ovNLd-SPLOHa_2KpLVI")

print("Available models:")

# Loop through the available models and print their details

for m in genai.list_models():

    # Check if the model supports the 'generateContent' method

    if 'generateContent' in m.supported_generation_methods:

        print(f"- {m.name}")
