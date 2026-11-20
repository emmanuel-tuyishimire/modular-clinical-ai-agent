# Modular Multi-Agent CLI Engine (Python)

A lightweight, extensible AI agent framework built in Python for **Stanford Code in Place X (Beyond CIPX)**. Rather than hardcoding tool logic into a single chat loop, this project separates the **agent execution engine** (`run_agent`) from pluggable **agent configurations** (`personality` + `tools` dictionary), allowing one loop to power multiple specialized assistants.

## Key Architectural Features

* **Reusable Agent Loop (`run_agent`):** Dynamically assembles system instructions from any agent's tool registry and executes multi-step reasoning loops (`Thought -> Tool Call -> Tool Result -> Response`).
* **Structured JSON Tool Protocol:** Enforces a strict JSON schema (`response_to_human` vs. `tool_call_request`) with defensive parsing (`parse_model_reply`) to eliminate brittle string slicing.
* **Hybrid Clinical Safety Design:** Combines deterministic Python clinical rules (objective vital-sign thresholds and inventory guards) with LLM natural-language reasoning so critical triage scores are never guessed by the model.
* **Built-In Guardrails:** Enforces a per-turn iteration ceiling (`MAX_TOOL_CALLS = 5`) to prevent infinite loops and gracefully returns error feedback to the model if an unrecognized tool is requested.

## Included Agents

### 1. Clinical Ward Triage & Supply Steward (Healthcare Spotlight)
Designed for nurses working in resource-constrained acute wards where high patient loads meet tight consumable supplies:
* **`admit_patient`:** Validates bed availability (preventing double-bookings) and deterministically classifies triage acuity (**RED**, **YELLOW**, or **GREEN**) from $\text{SpO}_2$, heart rate, and respiratory rate.
* **`get_ward_board`:** Displays active beds, calculated acuity tiers, chief complaints, and vital signs so the nurse can prioritize bedside care immediately.
* **`check_supplies` & `use_supply`:** Tracks critical ward consumables (`oxygen_cylinders`, `iv_fluid_bags`, `malaria_rdts`), blocks stock overdrafts, and triggers `[LOW STOCK ALERT]` warnings at reorder thresholds.
* **`discharge_patient`:** Safely clears a bed record and frees capacity for incoming admissions.

### 2. Priority To-Do List Agent
Manages daily tasks with `high` and `low` priority tags (`add_todo`, `list_todos`, `complete_todo`), automatically inspecting task numbers before marking items complete.

### 3. Personal Finance Tracker Agent
Logs categorized expenses and computes real-time totals (`add_expense`, `list_expenses`, `get_total`).

## Project Structure

```text
build-an-agent/
├── main.py           # Core multi-agent loop, JSON parser, and tool registries
├── ai.example.py     # Template for API client configuration (copy to ai.py)
├── notopenai/        # Course API client wrapper
├── .gitignore        # Excludes private ai.py credentials and cache files
└── README.md         # Project documentation
```

## Local Setup & Usage

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/](https://github.com/)<your-username>/modular-python-ai-agent.git
   cd modular-python-ai-agent
   ```

2. **Configure your API key:**
   Copy `ai.example.py` to `ai.py` and insert your API key:
   ```bash
   cp ai.example.py ai.py
   ```

3. **Run the multi-agent CLI:**
   ```bash
   python3 main.py
   ```

## Example Clinical Ward Session

```text
Which agent do you want to talk to?
1. To-do list
2. Finance tracker
3. Clinical Ward Triage & Supply Steward
> 3
Chatting with Clinical Ward Triage & Supply Steward! (press Enter to quit)
You: Admit Eric to Bed 1 with uncomplicated malaria, SpO2 97, HR 88, RR 18
    [tool call] admit_patient {'bed': 'Bed 1', 'name': 'Eric', 'complaint': 'uncomplicated malaria', 'spo2': 97, 'hr': 88, 'rr': 18}
Agent: Admitted Eric to Bed 1 (GREEN - Standard).
You: Admit Aline to Bed 2 with severe respiratory distress, SpO2 87, HR 126, RR 32
    [tool call] admit_patient {'bed': 'Bed 2', 'name': 'Aline', 'complaint': 'severe respiratory distress', 'spo2': 87, 'hr': 126, 'rr': 32}
Agent: Admitted Aline to Bed 2 as RED (Immediate) due to SpO2 87% and RR 32. Assess Aline immediately.
You: Start Aline on 1 oxygen cylinder and check our remaining supplies
    [tool call] use_supply {'item': 'oxygen_cylinders', 'quantity': 1}
    [tool call] check_supplies {}
Agent: Logged 1 oxygen cylinder used (2 remaining — LOW STOCK ALERT: reorder oxygen cylinders immediately). Other stock: 10 IV fluid bags, 20 malaria RDTs.
```