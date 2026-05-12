import re

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

rules = {
    "system_status_full": [
        r"(?:.*\s+)?check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:system|pc|computer|machine)\s*(?:condition|status|stats|health|performance|info|information|doing|running)?(?:.*)?",
        r"(?:.*\s+)?what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:system|pc|computer)\s+(?:condition|status|stats|health|performance|doing|like)(?:.*)?",
        r"(?:.*\s+)?how\s+(?:is|'s)\s+(?:my\s+)?(?:the\s+)?(?:system|pc|computer)\s*(?:doing|running|performing|condition)?(?:.*)?",
        r"(?:.*\s+)?report\s+(?:me\s+)?(?:my\s+)?(?:system|pc|computer)\s+(?:stats|status|condition|health|info|performance)(?:.*)?",
        r"(?:.*\s+)?(?:system|pc|computer)\s+(?:condition|status|stats|health|check|info|performance)(?:.*)?",
        r"(?:.*\s+)?tell\s+me\s+(?:about\s+)?(?:my\s+)?(?:system|pc|computer)\s*(?:stats|status|condition|info)?(?:.*)?",
    ],
    "check_ram_full": [
        r"(?:.*\s+)?check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:ram|memory|mem)\s*(?:usage|use|level|status|condition|doing)?(?:.*)?",
        r"(?:.*\s+)?what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:ram|memory)\s*(?:usage|use|used|level|like|at)?(?:.*)?",
        r"(?:.*\s+)?how\s+(?:much\s+)?(?:ram|memory)\s+(?:am\s+i\s+using|is\s+(?:being\s+)?used|do\s+i\s+have|is\s+(?:left|free|available))(?:.*)?",
        r"(?:.*\s+)?(?:ram|memory|mem)\s+(?:usage|use|check|status|level|info)(?:.*)?",
        r"(?:.*\s+)?show\s+(?:my\s+)?(?:ram|memory)\s*(?:usage|stats|info)?(?:.*)?",
    ],
    "check_cpu_full": [
        r"(?:.*\s+)?check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:cpu|processor|processing)\s*(?:usage|use|level|status|condition|doing|load)?(?:.*)?",
        r"(?:.*\s+)?what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:cpu|processor)\s*(?:usage|use|used|level|load|at)?(?:.*)?",
        r"(?:.*\s+)?how\s+(?:much\s+)?(?:cpu|processor)\s+(?:am\s+i\s+using|is\s+(?:being\s+)?used|is\s+it\s+at)(?:.*)?",
        r"(?:.*\s+)?(?:cpu|processor)\s+(?:usage|use|check|status|level|load|info)(?:.*)?",
        r"(?:.*\s+)?show\s+(?:my\s+)?(?:cpu|processor)\s*(?:usage|stats|info)?(?:.*)?",
    ],
    "check_disk_full": [
        r"(?:.*\s+)?check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:disk|storage|drive|hard\s*drive|ssd|hdd)\s*(?:usage|use|space|status|condition)?(?:.*)?",
        r"(?:.*\s+)?what(?:'s|s|\s+is)\s+(?:my\s+)?(?:the\s+)?(?:disk|storage|drive)\s*(?:space|usage|used|free|available|left)?(?:.*)?",
        r"(?:.*\s+)?how\s+(?:much\s+)?(?:disk\s+space|storage)\s+(?:do\s+i\s+have|is\s+(?:left|free|used|available))(?:.*)?",
        r"(?:.*\s+)?(?:disk|storage|drive)\s+(?:space|usage|use|check|status|info)(?:.*)?",
    ],
    "check_gpu_full": [
        r"(?:.*\s+)?check\s+(?:how(?:'s|s)?\s+)?(?:my\s+)?(?:the\s+)?(?:gpu|graphics\s*card|graphics|vram|video\s*card)\s*(?:condition|status|usage|info|doing)?(?:.*)?",
        r"(?:.*\s+)?what(?:'s|s|\s+is)\s+(?:my\s+)?(?:gpu|graphics\s*card|graphics)\s*(?:doing|status|condition|usage|temp(?:erature)?)?(?:.*)?",
        r"(?:.*\s+)?(?:gpu|graphics\s*card|graphics)\s+(?:status|info|check|condition|usage|temp(?:erature)?)(?:.*)?",
    ]
}

for t in tests:
    matched = False
    for rule, patterns in rules.items():
        for p in patterns:
            if re.fullmatch(p, t, re.IGNORECASE):
                matched = True
                print(f"OK: '{t}' matched {rule}")
                break
        if matched:
            break
    if not matched:
        print(f"FAIL: '{t}' didn't match any rule!")
