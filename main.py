import json
from ai import call_gpt

# --- GLOBAL CONSTANTS ---
# Four spaces used to visually indent tool calls and system status messages
INDENT = "    "

# Safety Net 1: Maximum consecutive tool calls allowed per user message
MAX_TOOL_CALLS = 5

# Universal JSON communication protocol shared by every agent
FORMAT = (
    "Reply with exactly one JSON dictionary, with no other text.\n"
    'To talk to the user: {"type": "response_to_human", "message": "..."}\n'
    'To use a tool: {"type": "tool_call_request", "tool_name": "...", "tool_parameters": {...}}\n'
    "Request one tool at a time, then stop. You will be shown the result and can reply again.\n"
    "Do not repeat a tool call you have already made for the same request."
)


# =====================================================================
# AGENT 1: TO-DO LIST AGENT (STATE, TOOLS & CONFIGURATION)
# =====================================================================

todos = []


def add_todo(parameters):
    """Tool: Adds a task dictionary {'task': ..., 'priority': ...} to todos."""
    task = parameters["task"]
    priority = parameters.get("priority", "low")
    todos.append({"task": task, "priority": priority})
    return f"Added: {task} ({priority})"


def list_todos(parameters):
    """Tool: Returns a numbered string showing each task and its priority."""
    if len(todos) == 0:
        return "The list is empty."

    lines = []
    for i in range(len(todos)):
        item = todos[i]
        lines.append(f"{i + 1}. {item['task']} ({item['priority']})")
    return "\n".join(lines)


def complete_todo(parameters):
    """Tool: Pops a 1-based task dictionary from todos and returns its task name."""
    number = int(parameters["number"])
    if number < 1 or number > len(todos):
        return "There is no task with that number."

    removed = todos.pop(number - 1)
    return "Completed: " + removed["task"]


TODO_PERSONALITY = "You are a helpful, focused productivity assistant. Keep replies short."

TODO_TOOLS = {
    "add_todo": {
        "function": add_todo,
        "description": 'parameters: {"task": "...", "priority": "high" or "low"}. Call it once for each task the user lists.',
    },
    "list_todos": {
        "function": list_todos,
        "description": "parameters: {}",
    },
    "complete_todo": {
        "function": complete_todo,
        "description": 'parameters: {"number": 1}. Use list_todos first to check the task number.',
    },
}

TODO_AGENT = {
    "name": "To-do list",
    "personality": TODO_PERSONALITY,
    "tools": TODO_TOOLS,
}


# =====================================================================
# AGENT 2: FINANCE TRACKER AGENT (STATE, TOOLS & CONFIGURATION)
# =====================================================================

expenses = []


def add_expense(parameters):
    """Tool: Records a new expense with a numeric amount and category label."""
    amount = float(parameters["amount"])
    category = parameters["category"]
    expenses.append({"amount": amount, "category": category})
    return f"Recorded {amount:.2f} for {category}."


def list_expenses(parameters):
    """Tool: Returns a numbered list of all recorded expenses."""
    if len(expenses) == 0:
        return "No expenses recorded yet."

    lines = []
    for i in range(len(expenses)):
        item = expenses[i]
        lines.append(f"{i + 1}. {item['category']}: {item['amount']:.2f}")
    return "\n".join(lines)


def get_total(parameters):
    """Tool: Calculates and returns the total spending across all recorded expenses."""
    total = 0.0
    for item in expenses:
        total += item["amount"]
    return f"Total spent: {total:.2f}"


FINANCE_PERSONALITY = "You are a precise, helpful personal finance assistant. Keep replies short."

FINANCE_TOOLS = {
    "add_expense": {
        "function": add_expense,
        "description": 'parameters: {"amount": 12.50, "category": "lunch"}. Call it once for each expense.',
    },
    "list_expenses": {
        "function": list_expenses,
        "description": "parameters: {}",
    },
    "get_total": {
        "function": get_total,
        "description": "parameters: {}",
    },
}

FINANCE_AGENT = {
    "name": "Finance tracker",
    "personality": FINANCE_PERSONALITY,
    "tools": FINANCE_TOOLS,
}


# =====================================================================
# AGENT 3: CLINICAL WARD TRIAGE & SUPPLY STEWARD (HEALTHCARE AGENT)
# =====================================================================

# In-memory list of active patient dictionaries on the ward
ward_patients = []

# Critical consumable stock levels for a resource-constrained acute ward
ward_supplies = {
    "oxygen_cylinders": 3,
    "iv_fluid_bags": 10,
    "malaria_rdts": 20,
}

# Reorder alert thresholds for each clinical supply item
LOW_STOCK_THRESHOLDS = {
    "oxygen_cylinders": 2,
    "iv_fluid_bags": 4,
    "malaria_rdts": 5,
}


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

    # Prevent double-booking an already occupied bed
    for patient in ward_patients:
        if patient["bed"].lower() == bed.lower():
            return f"Admission blocked: {patient['bed']} is already occupied by {patient['name']}."

    acuity = calculate_acuity(spo2, hr, rr)
    ward_patients.append({
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
    if len(ward_patients) == 0:
        return "The ward currently has no admitted patients."

    lines = []
    for p in ward_patients:
        lines.append(
            f"{p['bed']} - {p['name']} [{p['acuity']}]: {p['complaint']} "
            f"(SpO2 {p['spo2']}%, HR {p['hr']}, RR {p['rr']})"
        )
    return "\n".join(lines)


def check_supplies(parameters):
    """Tool: Reports current stock levels and flags any items at or below reorder thresholds."""
    lines = []
    for item, count in ward_supplies.items():
        alert = " [LOW STOCK]" if count <= LOW_STOCK_THRESHOLDS[item] else ""
        lines.append(f"{item}: {count}{alert}")
    return "\n".join(lines)


def use_supply(parameters):
    """Tool: Deducts used clinical supplies and triggers an immediate low-stock warning if needed."""
    item = str(parameters["item"]).lower().strip()
    quantity = int(parameters.get("quantity", 1))

    if item not in ward_supplies:
        valid_items = ", ".join(ward_supplies.keys())
        return f"Unknown supply '{item}'. Available items: {valid_items}."

    if quantity < 1:
        return "Quantity used must be at least 1."

    if ward_supplies[item] < quantity:
        return f"Stock error: Only {ward_supplies[item]} {item} remaining."

    ward_supplies[item] -= quantity
    remaining = ward_supplies[item]
    status = f"Logged {quantity} {item} used. Remaining: {remaining}."

    if remaining <= LOW_STOCK_THRESHOLDS[item]:
        status += f" [LOW STOCK ALERT: Reorder {item} immediately!]"
    return status


def discharge_patient(parameters):
    """Tool: Discharges a patient by bed label and frees the bed for new admissions."""
    bed = str(parameters["bed"]).strip()
    for i in range(len(ward_patients)):
        if ward_patients[i]["bed"].lower() == bed.lower():
            discharged = ward_patients.pop(i)
            return (
                f"Discharged {discharged['name']} from {discharged['bed']} "
                f"(Last acuity: {discharged['acuity']}). Bed is now open."
            )
    return f"No patient found in {bed}."


WARD_PERSONALITY = (
    "You are a concise, safety-focused clinical triage and ward resource steward "
    "supporting nurses in a resource-constrained hospital. Prioritize RED acuity patients first, "
    "highlight low oxygen or supply alerts immediately, and keep replies brief and actionable."
)

WARD_TOOLS = {
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
}

WARD_AGENT = {
    "name": "Clinical Ward Triage & Supply Steward",
    "personality": WARD_PERSONALITY,
    "tools": WARD_TOOLS,
}


# =====================================================================
# AGENT REGISTRY & REUSABLE ENGINE
# =====================================================================

AGENTS = {
    "1": TODO_AGENT,
    "2": FINANCE_AGENT,
    "3": WARD_AGENT,
}


def main():
    print("Which agent do you want to talk to?")
    for number in AGENTS:
        print(f"{number}. {AGENTS[number]['name']}")

    choice = input("> ")
    while choice not in AGENTS:
        print("Please enter a valid number from the menu.")
        choice = input("> ")

    run_agent(AGENTS[choice])


def parse_model_reply(reply):
    """Strips optional markdown code fences and parses the model's JSON string into a dict."""
    cleaned = reply.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Drop opening ```json and closing ``` lines if present
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    return json.loads(cleaned)


def run_agent(agent):
    """General-purpose agent loop capable of running any agent dictionary."""
    tools = agent["tools"]

    # Dynamically build the tool schema section from the chosen agent's dictionary
    tool_section = FORMAT + "\nTools:"
    for tool_name in tools:
        tool_section += f"\n{tool_name}, {tools[tool_name]['description']}"

    system_prompt = agent["personality"] + "\n" + tool_section
    messages = [make_message("system", system_prompt)]

    print(f"Chatting with {agent['name']}! (press Enter to quit)")

    while True:
        user_message = input("You: ")

        if user_message == "":
            break

        messages.append(make_message("user", user_message))

        tool_calls = 0
        is_working = True

        while is_working:
            prompt = format_messages(messages)
            reply = call_gpt(prompt)

            # Parse the model's JSON output safely
            parsed = parse_model_reply(reply)

            if parsed["type"] == "response_to_human":
                messages.append(make_message("assistant", reply))
                print("Agent: " + parsed["message"])
                is_working = False

            elif parsed["type"] == "tool_call_request":
                # Safety Net 1: Prevent runaway tool loops
                if tool_calls >= MAX_TOOL_CALLS:
                    print(f"{INDENT}Too many tool calls, so I stopped.")
                    is_working = False
                else:
                    tool_calls += 1
                    tool_name = parsed["tool_name"]
                    tool_parameters = parsed["tool_parameters"]

                    print(f"{INDENT}[tool call] {tool_name} {tool_parameters}")
                    messages.append(make_message("assistant", reply))

                    # Dynamic dispatch in one line
                    if tool_name in tools:
                        result = tools[tool_name]["function"](tool_parameters)
                    # Safety Net 2: Graceful recovery on unknown tools
                    else:
                        result = "Unknown tool: " + tool_name

                    messages.append(make_message("tool", result))


def make_message(role, content):
    """Creates and returns a single message dictionary."""
    return {"role": role, "content": content}


def format_messages(messages):
    """Serializes the list of message dictionaries into a single prompt string for GPT."""
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


if __name__ == "__main__":
    main()