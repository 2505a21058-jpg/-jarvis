"""
Generate all template skill .py files.
Run from project root: python scripts/generate_templates.py
"""

import os

TEMPLATES = {
    # 1-step
    "open": ("open", ["open"], "Opens an application or website"),
    "search": ("search", ["search"], "Searches for content in the active application"),
    "select": ("select", ["select"], "Selects or clicks a target element"),
    "type": ("type", ["type"], "Types text into a focused element"),
    "play": ("play", ["play"], "Presses the play button"),
    "scroll": ("scroll", ["scroll"], "Scrolls the active page"),
    "shortcut": ("shortcut", ["shortcut"], "Executes a keyboard shortcut"),
    "close_app": ("close", ["close"], "Closes the active window"),
    # 2-step
    "open_search": ("open_search", ["open", "search"], "Opens an app and searches"),
    "open_select": ("open_select", ["open", "select"], "Opens an app and selects a target"),
    "open_type": ("open_type", ["open", "type"], "Opens an app and types text"),
    "open_play": ("open_play", ["open", "play"], "Opens an app and plays media"),
    "open_scroll": ("open_scroll", ["open", "scroll"], "Opens an app and scrolls"),
    "open_close": ("open_close", ["open", "close"], "Opens and closes an app"),
    "search_select": ("search_select", ["search", "select"], "Searches and selects a result"),
    "search_play": ("search_play", ["search", "play"], "Searches and plays content"),
    "search_type": ("search_type", ["search", "type"], "Searches then types into a field"),
    "search_scroll": ("search_scroll", ["search", "scroll"], "Searches and scrolls results"),
    "select_type": ("select_type", ["select", "type"], "Selects a field and types into it"),
    "select_play": ("select_play", ["select", "play"], "Selects an item and plays it"),
    "select_shortcut": ("select_shortcut", ["select", "shortcut"], "Selects an item and triggers a shortcut"),
    "select_scroll": ("select_scroll", ["select", "scroll"], "Selects an item and scrolls"),
    "type_shortcut": ("type_shortcut", ["type", "shortcut"], "Types text then executes a shortcut"),
    "type_select": ("type_select", ["type", "select"], "Types text then selects a result"),
    "scroll_select": ("scroll_select", ["scroll", "select"], "Scrolls then selects an item"),
    "close_select": ("close_select", ["close", "select"], "Closes a window then selects something"),
    "close_open": ("close_open", ["close", "open"], "Closes a window then opens something"),
    "wait_select": ("wait_select", ["wait", "select"], "Waits then selects an element"),
    "wait_type": ("wait_type", ["wait", "type"], "Waits then types into a field"),
    "play_select": ("play_select", ["play", "select"], "Plays content then selects something"),
    # 3-step
    "open_search_select": ("open_search_select", ["open", "search", "select"], "Opens, searches, and selects a result"),
    "open_search_play": ("open_search_play", ["open", "search", "play"], "Opens, searches, and plays content"),
    "open_search_type": ("open_search_type", ["open", "search", "type"], "Opens, searches, and types"),
    "open_search_scroll": ("open_search_scroll", ["open", "search", "scroll"], "Opens, searches, and scrolls results"),
    "open_select_type": ("open_select_type", ["open", "select", "type"], "Opens, selects a field, and types"),
    "open_select_play": ("open_select_play", ["open", "select", "play"], "Opens, selects, and plays"),
    "open_select_shortcut": ("open_select_shortcut", ["open", "select", "shortcut"], "Opens, selects, and executes shortcut"),
    "open_type_select": ("open_type_select", ["open", "type", "select"], "Opens, types, and selects result"),
    "open_type_shortcut": ("open_type_shortcut", ["open", "type", "shortcut"], "Opens, types, and executes shortcut"),
    "open_play_type": ("open_play_type", ["open", "play", "type"], "Opens, plays, and types"),
    "open_scroll_select": ("open_scroll_select", ["open", "scroll", "select"], "Opens, scrolls, and selects"),
    "open_scroll_type": ("open_scroll_type", ["open", "scroll", "type"], "Opens, scrolls, and types"),
    "open_wait_type": ("open_wait_type", ["open", "wait", "type"], "Opens, waits, and types"),
    "open_wait_select": ("open_wait_select", ["open", "wait", "select"], "Opens, waits, and selects"),
    "open_tab_search": ("open_tab_search", ["open", "tab", "search"], "Opens, opens new tab, and searches"),
    "open_tab_type": ("open_tab_type", ["open", "tab", "type"], "Opens, opens new tab, and types"),
    "search_select_type": ("search_select_type", ["search", "select", "type"], "Searches, selects, and types"),
    "search_select_play": ("search_select_play", ["search", "select", "play"], "Searches, selects, and plays"),
    "search_scroll_select": ("search_scroll_select", ["search", "scroll", "select"], "Searches, scrolls, and selects"),
    "search_scroll_type": ("search_scroll_type", ["search", "scroll", "type"], "Searches, scrolls, and types"),
    "search_wait_select": ("search_wait_select", ["search", "wait", "select"], "Searches, waits, and selects"),
    "search_wait_scroll": ("search_wait_scroll", ["search", "wait", "scroll"], "Searches, waits, and scrolls"),
    "select_select_type": ("select_select_type", ["select", "select", "type"], "Selects, selects again, and types"),
    "select_type_select": ("select_type_select", ["select", "type", "select"], "Selects, types, and selects"),
    "select_play_select": ("select_play_select", ["select", "play", "select"], "Selects, plays, and selects"),
    "select_type_type": ("select_type_type", ["select", "type", "type"], "Selects then types twice"),
    "type_select_shortcut": ("type_select_shortcut", ["type", "select", "shortcut"], "Types, selects, and executes shortcut"),
    "type_type_type": ("type_type_type", ["type", "type", "type"], "Types text three times"),
    "close_select_open": ("close_select_open", ["close", "select", "open"], "Closes, selects, and opens"),
    "wait_scroll_select": ("wait_scroll_select", ["wait", "scroll", "select"], "Waits, scrolls, and selects"),
    "scroll_select_select": ("scroll_select_select", ["scroll", "select", "select"], "Scrolls and selects twice"),
    "select_select_play": ("select_select_play", ["select", "select", "play"], "Selects twice then plays"),
    # 4-step
    "open_search_select_select": ("open_search_select_select", ["open", "search", "select", "select"], "Opens, searches, and selects twice"),
    "open_search_select_play": ("open_search_select_play", ["open", "search", "select", "play"], "Opens, searches, selects, and plays"),
    "open_search_select_type": ("open_search_select_type", ["open", "search", "select", "type"], "Opens, searches, selects, and types"),
    "open_search_select_scroll": ("open_search_select_scroll", ["open", "search", "select", "scroll"], "Opens, searches, selects, and scrolls"),
    "open_search_select_shortcut": ("open_search_select_shortcut", ["open", "search", "select", "shortcut"], "Opens, searches, selects, and executes shortcut"),
    "open_search_search_select": ("open_search_search_select", ["open", "search", "search", "select"], "Opens, searches twice, and selects"),
    "open_search_scroll_select": ("open_search_scroll_select", ["open", "search", "scroll", "select"], "Opens, searches, scrolls, and selects"),
    "open_search_scroll_type": ("open_search_scroll_type", ["open", "search", "scroll", "type"], "Opens, searches, scrolls, and types"),
    "open_search_play_type": ("open_search_play_type", ["open", "search", "play", "type"], "Opens, searches, plays, and types"),
    "open_select_type_select": ("open_select_type_select", ["open", "select", "type", "select"], "Opens, selects, types, and selects"),
    "open_select_type_shortcut": ("open_select_type_shortcut", ["open", "select", "type", "shortcut"], "Opens, selects, types, and executes shortcut"),
    "open_select_play_select": ("open_select_play_select", ["open", "select", "play", "select"], "Opens, selects, plays, and selects"),
    "open_select_type_type": ("open_select_type_type", ["open", "select", "type", "type"], "Opens, selects, and types twice"),
    "open_type_select_shortcut": ("open_type_select_shortcut", ["open", "type", "select", "shortcut"], "Opens, types, selects, and executes shortcut"),
    "open_scroll_select_select": ("open_scroll_select_select", ["open", "scroll", "select", "select"], "Opens, scrolls, and selects twice"),
    "open_tab_search_select": ("open_tab_search_select", ["open", "tab", "search", "select"], "Opens, opens tab, searches, and selects"),
    "open_tab_search_type": ("open_tab_search_type", ["open", "tab", "search", "type"], "Opens, opens tab, searches, and types"),
    "open_wait_search_select": ("open_wait_search_select", ["open", "wait", "search", "select"], "Opens, waits, searches, and selects"),
    "open_search_wait_select": ("open_search_wait_select", ["open", "search", "wait", "select"], "Opens, searches, waits, and selects"),
    "search_select_type_select": ("search_select_type_select", ["search", "select", "type", "select"], "Searches, selects, types, and selects"),
    "search_scroll_select_select": ("search_scroll_select_select", ["search", "scroll", "select", "select"], "Searches, scrolls, and selects twice"),
    "search_scroll_type_select": ("search_scroll_type_select", ["search", "scroll", "type", "select"], "Searches, scrolls, types, and selects"),
    "search_select_wait_select": ("search_select_wait_select", ["search", "select", "wait", "select"], "Searches, selects, waits, and selects"),
    "search_wait_select_select": ("search_wait_select_select", ["search", "wait", "select", "select"], "Searches, waits, and selects twice"),
    "select_type_select_type": ("select_type_select_type", ["select", "type", "select", "type"], "Selects, types, selects, types"),
    "scroll_select_select_select": ("scroll_select_select_select", ["scroll", "select", "select", "select"], "Scrolls and selects three times"),
    "close_select_open_select": ("close_select_open_select", ["close", "select", "open", "select"], "Closes, selects, opens, and selects"),
    "select_select_play_scroll": ("select_select_play_scroll", ["select", "select", "play", "scroll"], "Selects twice, plays, and scrolls"),
    # 5-step
    "open_search_select_select_select": ("open_search_select_select_select", ["open", "search", "select", "select", "select"], "Opens, searches, and selects three times"),
    "open_search_select_select_play": ("open_search_select_select_play", ["open", "search", "select", "select", "play"], "Opens, searches, selects twice, and plays"),
    "open_search_select_select_type": ("open_search_select_select_type", ["open", "search", "select", "select", "type"], "Opens, searches, selects twice, and types"),
    "open_search_select_select_scroll": ("open_search_select_select_scroll", ["open", "search", "select", "select", "scroll"], "Opens, searches, selects twice, and scrolls"),
    "open_search_scroll_select_select": ("open_search_scroll_select_select", ["open", "search", "scroll", "select", "select"], "Opens, searches, scrolls, and selects twice"),
    "open_search_search_select_select": ("open_search_search_select_select", ["open", "search", "search", "select", "select"], "Opens, searches twice, and selects twice"),
    "open_search_select_type_select": ("open_search_select_type_select", ["open", "search", "select", "type", "select"], "Opens, searches, selects, types, and selects"),
    "open_search_select_play_select": ("open_search_select_play_select", ["open", "search", "select", "play", "select"], "Opens, searches, selects, plays, and selects"),
    "open_search_scroll_select_type": ("open_search_scroll_select_type", ["open", "search", "scroll", "select", "type"], "Opens, searches, scrolls, selects, and types"),
    "open_search_scroll_type_select": ("open_search_scroll_type_select", ["open", "search", "scroll", "type", "select"], "Opens, searches, scrolls, types, and selects"),
    "open_tab_search_select_select": ("open_tab_search_select_select", ["open", "tab", "search", "select", "select"], "Opens, opens tab, searches, and selects twice"),
    "open_tab_search_play_select": ("open_tab_search_play_select", ["open", "tab", "search", "play", "select"], "Opens, opens tab, searches, plays, and selects"),
    "open_select_type_select_select": ("open_select_type_select_select", ["open", "select", "type", "select", "select"], "Opens, selects, types, and selects twice"),
    "open_select_select_type_select": ("open_select_select_type_select", ["open", "select", "select", "type", "select"], "Opens, selects twice, types, and selects"),
    "open_wait_search_select_select": ("open_wait_search_select_select", ["open", "wait", "search", "select", "select"], "Opens, waits, searches, and selects twice"),
    "open_search_wait_select_select": ("open_search_wait_select_select", ["open", "search", "wait", "select", "select"], "Opens, searches, waits, and selects twice"),
    "search_select_select_type_select": ("search_select_select_type_select", ["search", "select", "select", "type", "select"], "Searches, selects twice, types, and selects"),
    "search_scroll_select_select_select": ("search_scroll_select_select_select", ["search", "scroll", "select", "select", "select"], "Searches, scrolls, and selects three times"),
    "search_scroll_select_type_select": ("search_scroll_select_type_select", ["search", "scroll", "select", "type", "select"], "Searches, scrolls, selects, types, and selects"),
    "search_select_wait_select_select": ("search_select_wait_select_select", ["search", "select", "wait", "select", "select"], "Searches, selects, waits, and selects twice"),
    "search_wait_select_select_select": ("search_wait_select_select_select", ["search", "wait", "select", "select", "select"], "Searches, waits, and selects three times"),
    "select_type_shortcut_wait_select": ("select_type_shortcut_wait_select", ["select", "type", "shortcut", "wait", "select"], "Selects, types, shortcut, waits, and selects"),
    "scroll_select_select_select_select": ("scroll_select_select_select_select", ["scroll", "select", "select", "select", "select"], "Scrolls and selects four times"),
}


def pascal(snake: str) -> str:
    return "".join(word.capitalize() for word in snake.split("_"))


def generate_template(skills_dir: str, name: str, class_suffix: str, steps: list[str], desc: str):
    cls_name = pascal(name) + "Skill"
    steps_repr = repr(steps)
    content = f'''"""skills/templates/{name}.py"""
from skills.step_runner import StepRunnerSkill


class {cls_name}(StepRunnerSkill):
    name = "{name}"
    description = "{desc}"
    STEPS = {steps_repr}
'''
    filepath = os.path.join(skills_dir, "templates", f"{name}.py")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(content)


def generate_manifest(skills_dir: str, name: str, steps: list[str], desc: str):
    """Generate a SKILL.md manifest file in skills/manifests/."""
    content = [
        "---",
        f'name: {name.replace("_", "-")}',
        f"description: {desc}",
        "version: \"1.0\"",
    ]
    if steps:
        content.append("steps:")
        for s in steps:
            content.append(f"  - {s}")
    content.append("---")
    content.append("")

    filepath = os.path.join(skills_dir, "manifests", f"{name.replace('_', '-')}.skill.md")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write("\n".join(content))


def main():
    base = os.path.join(os.path.dirname(__file__), "..", "skills")
    # Create template files in skills/templates/
    for name, (class_suffix, steps, desc) in TEMPLATES.items():
        generate_template(base, name, class_suffix, steps, desc)
        print(f"  Created skills/templates/{name}.py")

    # Create SKILL.md manifest files in skills/manifests/
    for name, (class_suffix, steps, desc) in TEMPLATES.items():
        generate_manifest(base, name, steps, desc)
        print(f"  Created skills/manifests/{name.replace('_', '-')}.skill.md")

    # Compatibility modules are hand-maintained wrappers because some of them
    # preserve legacy class names, policy behavior, or browser-specific state.
    print("  Left compatibility wrappers unchanged")

    # Generate __init__.py for templates package
    init_lines = ['"""skills/templates/ - Generated template skills."""\n']
    for name in sorted(TEMPLATES):
        cls_name = pascal(name) + "Skill"
        init_lines.append(f"from skills.templates.{name} import {cls_name}")
    init_lines.append("")
    with open(os.path.join(base, "templates", "__init__.py"), "w") as f:
        f.write("\n".join(init_lines))
    print(f"\nTotal: {len(TEMPLATES)} templates generated")

    # Print bootstrap code for __init__.py
    print("\n--- Add these to skills/__init__.py bootstrap_skills() ---")
    for name in sorted(TEMPLATES):
        cls_name = pascal(name) + "Skill"
        print(f"    from skills.templates.{name} import {cls_name}")


if __name__ == "__main__":
    main()
