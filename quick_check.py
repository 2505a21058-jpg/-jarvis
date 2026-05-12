import sys
sys.path.insert(0, ".")
from agent.gate import GateLayer, GATE_RULES
g = GateLayer(list(GATE_RULES))

tests = [
    "check hows my system",
    "check hows my system and report me its stats",
    "yeah check hows my system",
    "whats my cpu usage",
    "what is my ram usage",
    "check my ram usage",
    "how much ram am i using",
    "check my system condition",
    "system stats",
    "report my system stats",
    "show my cpu",
    "check my gpu condition",
]

all_pass = True
for t in tests:
    r = g.evaluate(t)
    ok = r.resolved and r.skill_name == "system_monitor"
    status = f"OK  -> {r.skill_name}" if ok else f"FAIL-> {r.skill_name if r.resolved else 'UNRESOLVED'}"
    if not ok:
        all_pass = False
    print(f"  {status}: '{t}'")

print(f"\n{'All PASSED' if all_pass else 'FAILURES DETECTED'}")
