import json
import urllib.error
import urllib.request
import streamlit as st
from google import genai
from google.genai import errors, types

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Modular Multi-Agent Clinical & Productivity Assistant",
    page_icon="🏥",
    layout="wide",
)

# --- GLOBAL CONSTANTS ---
MAX_TOOL_CALLS = 6

FORMAT = (
    "Reply with exactly one JSON dictionary, with no other text.\n"
    'To talk to the user: {"type": "response_to_human", "message": "..."}\n'
    'To use a tool: {"type": "tool_call_request", "tool_name": "...", "tool_parameters": {...}}\n'
    "Request one tool at a time, then stop. You will be shown the result and can reply again.\n"
    "Complete ALL requested actions or calculations in sequence before sending response_to_human.\n"
    "Do not repeat a tool call you have already made with the same parameters."
)

LOW_STOCK_THRESHOLDS = {
    "oxygen_cylinders": 2,
    "iv_fluid_bags": 4,
    "malaria_rdts": 5,
}


# =====================================================================
# 1. INITIALIZE BROWSER MEMORY (st.session_state)
# =====================================================================

if "ward_patients" not in st.session_state:
    st.session_state.ward_patients = []

if "ward_supplies" not in st.session_state:
    st.session_state.ward_supplies = {
        "oxygen_cylinders": 3,
        "iv_fluid_bags": 10,
        "malaria_rdts": 20,
    }

if "todos" not in st.session_state:
    st.session_state.todos = []

if "expenses" not in st.session_state:
    st.session_state.expenses = []

if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {
        "Clinical Ward Triage & Supply Steward": [],
        "To-do list": [],
        "Finance tracker": [],
    }


# =====================================================================
# 2. CLINICAL WARD TRIAGE & SUPPLY TOOLS (AGENT 1)
# =====================================================================

def calculate_acuity(spo2, hr, rr):
    """Deterministically classifies patient triage acuity from objective vital signs."""
    if spo2 < 90 or rr > 30 or hr > 130:
        return "RED (Immediate)"
    elif spo2 <= 93 or rr > 22 or hr > 110:
        return "YELLOW (Urgent)"
    else:
        return "GREEN (Standard)"


def admit_patient(parameters):
    """Tool: Admits a patient to a free bed and computes objective triage acuity."""
    bed = str(parameters["bed"]).strip()
    name = str(parameters["name"]).strip()
    complaint = str(parameters["complaint"]).strip()
    spo2 = int(parameters["spo2"])
    hr = int(parameters["hr"])
    rr = int(parameters["rr"])

    for patient in st.session_state.ward_patients:
        if patient["bed"].lower() == bed.lower():
            return f"Admission blocked: {patient['bed']} is already occupied by {patient['name']}."

    acuity = calculate_acuity(spo2, hr, rr)
    st.session_state.ward_patients.append({
        "bed": bed,
        "name": name,
        "complaint": complaint,
        "spo2": spo2,
        "hr": hr,
        "rr": rr,
        "acuity": acuity,
    })
    return f"Admitted {name} to {bed} | Acuity: {acuity} | SpO2: {spo2}%, HR: {hr}, RR: {rr}"


def get_ward_board(parameters):
    """Tool: Returns all admitted patients with their bed, acuity tier, and vital signs."""
    if len(st.session_state.ward_patients) == 0:
        return "The ward currently has no admitted patients."

    lines = []
    for p in st.session_state.ward_patients:
        lines.append(
            f"{p['bed']} - {p['name']} [{p['acuity']}]: {p['complaint']} "
            f"(SpO2 {p['spo2']}%, HR {p['hr']}, RR {p['rr']})"
        )
    return "\n".join(lines)


def check_supplies(parameters):
    """Tool: Reports current stock levels and flags any items at or below reorder thresholds."""
    lines = []
    for item, count in st.session_state.ward_supplies.items():
        alert = " [LOW STOCK]" if count <= LOW_STOCK_THRESHOLDS[item] else ""
        lines.append(f"{item}: {count}{alert}")
    return "\n".join(lines)


def use_supply(parameters):
    """Tool: Deducts used clinical supplies and triggers an immediate low-stock warning if needed."""
    item = str(parameters["item"]).lower().strip()
    quantity = int(parameters.get("quantity", 1))

    if item not in st.session_state.ward_supplies:
        valid_items = ", ".join(st.session_state.ward_supplies.keys())
        return f"Unknown supply '{item}'. Available items: {valid_items}."

    if quantity < 1:
        return "Quantity used must be at least 1."

    if st.session_state.ward_supplies[item] < quantity:
        return f"Stock error: Only {st.session_state.ward_supplies[item]} {item} remaining."

    st.session_state.ward_supplies[item] -= quantity
    remaining = st.session_state.ward_supplies[item]
    status = f"Logged {quantity} {item} used. Remaining: {remaining}."

    if remaining <= LOW_STOCK_THRESHOLDS[item]:
        status += f" [LOW STOCK ALERT: Reorder {item} immediately!]"
    return status


def discharge_patient(parameters):
    """Tool: Discharges a patient by bed label and frees the bed for new admissions."""
    bed = str(parameters["bed"]).strip()
    for i in range(len(st.session_state.ward_patients)):
        if st.session_state.ward_patients[i]["bed"].lower() == bed.lower():
            discharged = st.session_state.ward_patients.pop(i)
            return (
                f"Discharged {discharged['name']} from {discharged['bed']} "
                f"(Last acuity: {discharged['acuity']}). Bed is now open."
            )
    return f"No patient found in {bed}."


WARD_AGENT = {
    "name": "Clinical Ward Triage & Supply Steward",
    "personality": (
        "You are a concise, safety-focused clinical triage and ward resource steward "
        "supporting nurses in a resource-constrained hospital. Prioritize RED acuity patients first, "
        "highlight low oxygen or supply alerts immediately, and keep replies brief and actionable."
    ),
    "tools": {
        "admit_patient": {
            "function": admit_patient,
            "description": (
                'parameters: {"bed": "Bed 1", "name": "Aline", "complaint": "dyspnea", '
                '"spo2": 88, "hr": 122, "rr": 28}. Call once per patient.'
            ),
        },
        "get_ward_board": {
            "function": get_ward_board,
            "description": "parameters: {}. Lists all admitted patients, vitals, and acuity levels.",
        },
        "check_supplies": {
            "function": check_supplies,
            "description": "parameters: {}. Checks current stock of oxygen_cylinders, iv_fluid_bags, and malaria_rdts.",
        },
        "use_supply": {
            "function": use_supply,
            "description": (
                'parameters: {"item": "oxygen_cylinders" | "iv_fluid_bags" | "malaria_rdts", "quantity": 1}. '
                "Deducts used supplies from ward stock."
            ),
        },
        "discharge_patient": {
            "function": discharge_patient,
            "description": 'parameters: {"bed": "Bed 1"}. Discharges a patient and frees their bed.',
        },
    },
}


# =====================================================================
# 3. TO-DO & FINANCE AGENTS (AGENTS 2 & 3)
# =====================================================================

def add_todo(parameters):
    task = parameters["task"]
    priority = parameters.get("priority", "low")
    st.session_state.todos.append({"task": task, "priority": priority})
    return f"Added: {task} ({priority})"


def list_todos(parameters):
    if len(st.session_state.todos) == 0:
        return "The list is empty."
    return "\n".join(
        f"{i + 1}. {item['task']} ({item['priority']})"
        for i, item in enumerate(st.session_state.todos)
    )


def complete_todo(parameters):
    number = int(parameters["number"])
    if number < 1 or number > len(st.session_state.todos):
        return "There is no task with that number."
    removed = st.session_state.todos.pop(number - 1)
    return "Completed: " + removed["task"]


TODO_AGENT = {
    "name": "To-do list",
    "personality": "You are a helpful, focused productivity assistant. Keep replies short.",
    "tools": {
        "add_todo": {
            "function": add_todo,
            "description": 'parameters: {"task": "...", "priority": "high" or "low"}. Call once per task.',
        },
        "list_todos": {"function": list_todos, "description": "parameters: {}"},
        "complete_todo": {
            "function": complete_todo,
            "description": 'parameters: {"number": 1}. Use list_todos first to check the task number.',
        },
    },
}


def add_expense(parameters):
    amount = float(parameters["amount"])
    category = parameters["category"]
    st.session_state.expenses.append({"amount": amount, "category": category})
    return f"Recorded {amount:.2f} for {category}."


def list_expenses(parameters):
    if len(st.session_state.expenses) == 0:
        return "No expenses recorded yet."
    return "\n".join(
        f"{i + 1}. {item['category']}: {item['amount']:.2f}"
        for i, item in enumerate(st.session_state.expenses)
    )


def get_total(parameters):
    total = sum(item["amount"] for item in st.session_state.expenses)
    return f"Total spent: {total:.2f}"


FINANCE_AGENT = {
    "name": "Finance tracker",
    "personality": "You are a precise, helpful personal finance assistant. Keep replies short.",
    "tools": {
        "add_expense": {
            "function": add_expense,
            "description": 'parameters: {"amount": 12.50, "category": "lunch"}. Call once per expense.',
        },
        "list_expenses": {"function": list_expenses, "description": "parameters: {}"},
        "get_total": {"function": get_total, "description": "parameters: {}"},
    },
}

AGENTS = {
    "Clinical Ward Triage & Supply Steward": WARD_AGENT,
    "To-do list": TODO_AGENT,
    "Finance tracker": FINANCE_AGENT,
}


# =====================================================================
# 4. AI CONNECTION & PROMPT HELPERS
# =====================================================================

@st.cache_resource
def get_gemini_client(api_key):
    """Reuses a single Gemini client connection across messages."""
    return genai.Client(api_key=api_key)


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
        "max_tokens": 450,
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


def try_gemini(prompt, gemini_key):
    """Calls Google Gemini models with automatic fallback between Flash tiers."""
    client = get_gemini_client(gemini_key)
    last_err = ""
    for model_name in ["gemini-3.8-flash", "gemini-3.5-flash-lite"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=450,
                ),
            )
            return response.text, ""
        except (errors.ServerError, errors.ClientError) as e:
            last_err = f"{model_name}: {e.message}"
            continue
    return None, last_err


def call_llm(prompt, gemini_key, groq_key, engine_choice):
    """Routes to the selected AI engine (Auto, Google Gemini, or Groq)."""
    groq_error = ""
    gemini_error = ""

    if engine_choice == "Google Gemini" and gemini_key:
        text, gemini_error = try_gemini(prompt, gemini_key)
        if text:
            return text

    elif engine_choice == "Groq" and groq_key:
        try:
            return call_groq(prompt, groq_key)
        except Exception as e:
            groq_error = str(e)

    else:
        # Auto mode: Fast Groq primary + Google Gemini automatic backup
        if groq_key:
            try:
                return call_groq(prompt, groq_key)
            except urllib.error.HTTPError as e:
                groq_error = f"Groq HTTP {e.code}"
            except Exception as e:
                groq_error = str(e)

        if gemini_key:
            text, gemini_error = try_gemini(prompt, gemini_key)
            if text:
                return text

    return json.dumps({
        "type": "response_to_human",
        "message": f"AI connection issue ({groq_error or gemini_error or 'no active key'}). Please try again shortly.",
    })


def parse_model_reply(reply):
    """Extracts and parses the model's JSON dictionary even if wrapped in extra text or fences."""
    cleaned = reply.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def format_messages(messages):
    """Serializes the list of message dictionaries into a single prompt string."""
    result = ""
    for message in messages:
        if message["role"] == "system":
            result += f"Instructions: {message['content']}\n\n"
        elif message["role"] == "user":
            result += f"User: {message['content']}\n"
        elif message["role"] == "assistant":
            result += f"Assistant: {message['content']}\n"
        elif message["role"] == "tool":
            result += f"Tool result: {message['content']}\n"
    result += "Assistant:"
    return result


# =====================================================================
# 5. STREAMLIT WEB INTERFACE
# =====================================================================

with st.sidebar:
    st.title("⚙️ Agent Controls")
    selected_name = st.selectbox("Choose an Agent:", list(AGENTS.keys()))
    active_agent = AGENTS[selected_name]

    try:
        server_gemini = st.secrets.get("GEMINI_API_KEY", None)
        server_groq = st.secrets.get("GROQ_API_KEY", None)
    except Exception:
        server_gemini = None
        server_groq = None

    engine_choice = st.selectbox(
        "AI Engine:",
        ["Auto (Groq + Gemini Backup)", "Google Gemini", "Groq"],
    )

    st.divider()

    if server_groq or server_gemini:
        gemini_key = server_gemini
        groq_key = server_groq
        st.success("Connected via server keys")
    else:
        gemini_key = st.text_input("Enter Gemini API Key:", type="password")
        groq_key = None

    if st.button("Clear Current Chat"):
        st.session_state.chat_histories[selected_name] = []
        st.rerun()

st.title(f"🏥 {active_agent['name']}")
st.caption("Modular Multi-Agent AI Engine — Powered by Multi-Step Natural-Language Tool Calling")

# Live Visual Status Panel for the Clinical Ward Agent
if selected_name == "Clinical Ward Triage & Supply Steward":
    st.subheader("Live Ward Supply & Bed Monitor")
    col1, col2, col3 = st.columns(3)
    supplies = st.session_state.ward_supplies

    col1.metric(
        "🫁 Oxygen Cylinders",
        supplies["oxygen_cylinders"],
        delta="LOW STOCK" if supplies["oxygen_cylinders"] <= LOW_STOCK_THRESHOLDS["oxygen_cylinders"] else "OK",
        delta_color="inverse" if supplies["oxygen_cylinders"] <= LOW_STOCK_THRESHOLDS["oxygen_cylinders"] else "normal",
    )
    col2.metric(
        "💧 IV Fluid Bags",
        supplies["iv_fluid_bags"],
        delta="LOW STOCK" if supplies["iv_fluid_bags"] <= LOW_STOCK_THRESHOLDS["iv_fluid_bags"] else "OK",
        delta_color="inverse" if supplies["iv_fluid_bags"] <= LOW_STOCK_THRESHOLDS["iv_fluid_bags"] else "normal",
    )
    col3.metric(
        "🧪 Malaria RDTs",
        supplies["malaria_rdts"],
        delta="LOW STOCK" if supplies["malaria_rdts"] <= LOW_STOCK_THRESHOLDS["malaria_rdts"] else "OK",
        delta_color="inverse" if supplies["malaria_rdts"] <= LOW_STOCK_THRESHOLDS["malaria_rdts"] else "normal",
    )

    if st.session_state.ward_patients:
        st.markdown("**Active Ward Beds:**")
        for p in st.session_state.ward_patients:
            badge = "🔴" if "RED" in p["acuity"] else ("🟡" if "YELLOW" in p["acuity"] else "🟢")
            st.info(
                f"{badge} **{p['bed']} — {p['name']}** | **{p['acuity']}** | "
                f"Complaint: {p['complaint']} (SpO2: {p['spo2']}%, HR: {p['hr']}, RR: {p['rr']})"
            )
    else:
        st.info("No patients currently admitted. Try typing: *Admit Aline to Bed 1 with dyspnea, SpO2 87, HR 126, RR 32*")

    st.divider()

# Display existing chat messages for the active agent
history = st.session_state.chat_histories[selected_name]
for msg in history:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.write(msg["content"])
    elif msg["role"] == "assistant":
        try:
            parsed_hist = parse_model_reply(msg["content"])
            if parsed_hist["type"] == "response_to_human":
                with st.chat_message("assistant"):
                    st.write(parsed_hist["message"])
        except Exception:
            pass

# Chat input box at the bottom of the webpage
user_message = st.chat_input(f"Message {active_agent['name']}...")

if user_message:
    if not gemini_key and not groq_key:
        st.warning("Please configure an API key in the sidebar or Streamlit Secrets.")
        st.stop()

    history.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.write(user_message)

    tools = active_agent["tools"]
    tool_section = FORMAT + "\nTools:"
    for tool_name in tools:
        tool_section += f"\n{tool_name}, {tools[tool_name]['description']}"
    system_prompt = active_agent["personality"] + "\n" + tool_section

    tool_calls = 0
    is_working = True

    with st.chat_message("assistant"):
        with st.spinner("Agent reasoning and running tools..."):
            while is_working:
                full_messages = [{"role": "system", "content": system_prompt}] + history
                prompt = format_messages(full_messages)
                reply = call_llm(prompt, gemini_key, groq_key, engine_choice)

                try:
                    parsed = parse_model_reply(reply)
                except Exception:
                    history.append({"role": "assistant", "content": reply})
                    st.write(reply)
                    is_working = False
                    break

                if parsed["type"] == "response_to_human":
                    history.append({"role": "assistant", "content": reply})
                    st.write(parsed["message"])
                    is_working = False

                elif parsed["type"] == "tool_call_request":
                    if tool_calls >= MAX_TOOL_CALLS:
                        st.warning("Too many tool calls, so I stopped.")
                        is_working = False
                    else:
                        tool_calls += 1
                        tool_name = parsed["tool_name"]
                        tool_parameters = parsed["tool_parameters"]
                        history.append({"role": "assistant", "content": reply})

                        if tool_name in tools:
                            result = tools[tool_name]["function"](tool_parameters)
                        else:
                            result = "Unknown tool: " + tool_name

                        history.append({"role": "tool", "content": result})

    st.rerun()