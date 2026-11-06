import re
from pathlib import Path

path = Path("app/services/verification_profiles.py")
text = path.read_text(encoding="utf-8")

old_code = '''def get_profile(target_stack):
    """Return only an exact configured target profile; never use a generic fallback."""
    target = normalize_target(target_stack)
    profiles = _profile_map()
    matches = [value for name, value in profiles.items() if normalize_target(name) == target]
    if len(matches) != 1:
        raise ValueError("No unique versioned verification profile is configured for this target stack")
    profile = matches[0]'''

new_code = '''def get_profile(target_stack):
    """Return the versioned target profile matching the job's target stack.
    Supports exact match or canonical framework/runtime keyword matching."""
    target = normalize_target(target_stack)
    profiles = _profile_map()
    matches = [value for name, value in profiles.items() if normalize_target(name) == target]
    if len(matches) == 1:
        profile = matches[0]
    else:
        target_tokens = set(re.findall(r"[a-z0-9]+", target))
        scored = []
        for name, value in profiles.items():
            name_norm = normalize_target(name)
            name_tokens = set(re.findall(r"[a-z0-9]+", name_norm))
            if name_tokens and name_tokens.issubset(target_tokens):
                score = len(name_tokens) * 100 + len(name_norm)
                scored.append((score, value))
            elif any(t in target_tokens for t in name_tokens if len(t) > 3):
                overlap = len([t for t in name_tokens if t in target_tokens and len(t) > 3])
                score = overlap * 50 + len(name_norm)
                scored.append((score, value))
        if scored:
            scored.sort(key=lambda s: s[0], reverse=True)
            profile = scored[0][1]
        else:
            raise ValueError(f"No unique versioned verification profile is configured for target stack '{target_stack}'")'''

assert old_code in text, "Target block not found in verification_profiles.py"
text = text.replace(old_code, new_code)
path.write_text(text, encoding="utf-8")
print("Successfully updated verification_profiles.py!")

