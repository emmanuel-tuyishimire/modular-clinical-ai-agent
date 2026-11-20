from notopenai import NotOpenAI

# Replace with your personal API key, then save this file as ai.py
API_KEY = "noai-YOUR-KEY-HERE"

client = NotOpenAI(api_key=API_KEY)


def call_gpt(prompt):
    """Sends a text prompt to gpt-5-nano and returns the model's plain text reply."""
    response = client.responses.create(
        model="gpt-5-nano",
        input=prompt,
    )
    return response.output_text