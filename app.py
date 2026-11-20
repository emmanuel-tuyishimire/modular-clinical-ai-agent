@st.cache_data(ttl=3600)
def get_groq_model(groq_key):
    """Fetches Groq's active models list and picks an available chat model automatically."""
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={
            "Authorization": f"Bearer {groq_key}",
            "User-Agent": "Mozilla/5.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        models = [m["id"] for m in data.get("data", []) if "id" in m]

    skip_words = ("whisper", "tts", "guard", "embed", "vision")
    chat_models = [m for m in models if not any(w in m.lower() for w in skip_words)]

    for keyword in ("llama", "versatile", "instant", "qwen", "gemma"):
        for m in chat_models:
            if keyword in m.lower():
                return m

    return chat_models[0] if chat_models else models[0]


def call_groq(prompt, groq_key):
    """Calls Groq's fast inference API using an auto-detected active model."""
    model_id = get_groq_model(groq_key)
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 300,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def call_llm(prompt, gemini_key, groq_key):
    """Routes to Groq first for sub-second speed, with automatic fallback to Gemini."""
    groq_error = ""
    if groq_key:
        try:
            return call_groq(prompt, groq_key)
        except urllib.error.HTTPError as e:
            details = e.read().decode("utf-8", errors="ignore")
            groq_error = f"Groq HTTP {e.code}: {details}"
        except Exception as e:
            groq_error = f"Groq error: {e}"

    if gemini_key:
        client = get_gemini_client(gemini_key)
        for model_name in ["gemini-3.8-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=300,
                    ),
                )
                return response.text
            except (errors.ServerError, errors.ClientError):
                continue

    return json.dumps({
        "type": "response_to_human",
        "message": f"AI connection issue ({groq_error or 'all models busy'}). Please try again shortly.",
    })