from pathlib import Path

target_file = Path("backend/app/services/phase6_service.py")
content = target_file.read_text(encoding="utf-8")

old_part = """        if isinstance(output, dict) and "content" in output:
            from app.services.phase5_engine import (
                strict_adapter_object,
                reject_json_constant,
            )

            raw_str = output["content"].strip()
            if raw_str.startswith("```json"):
                raw_str = raw_str[7:]
            elif raw_str.startswith("```"):
                raw_str = raw_str[3:]
            if raw_str.endswith("```"):
                raw_str = raw_str[:-3]
            raw_str = raw_str.strip()

            try:
                output = json.loads(
                    raw_str,
                    object_pairs_hook=strict_adapter_object,
                    parse_constant=reject_json_constant,
                )
            except ValueError as ve:
                if "Duplicate adapter JSON key" in str(ve):
                    logger.warning("Duplicate key in model JSON output; falling back to standard json.loads")
                    output = json.loads(raw_str)
                else:
                    raise
        changes = ChangeSet.model_validate(output)"""

new_part = """        if trace.get("provider_metadata", {}).get("finish_reason") == "length":
            raise IncompleteModelOutputError("Model response was truncated due to output token ceiling limit.")
        if isinstance(output, dict) and "content" in output:
            from app.services.phase5_engine import (
                strict_adapter_object,
                reject_json_constant,
            )

            raw_str = output["content"].strip()
            if raw_str.startswith("```json"):
                raw_str = raw_str[7:]
            elif raw_str.startswith("```"):
                raw_str = raw_str[3:]
            if raw_str.endswith("```"):
                raw_str = raw_str[:-3]
            raw_str = raw_str.strip()

            try:
                output = json.loads(
                    raw_str,
                    object_pairs_hook=strict_adapter_object,
                    parse_constant=reject_json_constant,
                )
            except json.JSONDecodeError as jde:
                raise MalformedModelOutputError(f"Malformed or truncated model JSON output: {jde}") from jde
            except ValueError as ve:
                if "Duplicate adapter JSON key" in str(ve):
                    logger.warning("Duplicate key in model JSON output; falling back to standard json.loads")
                    try:
                        output = json.loads(raw_str)
                    except json.JSONDecodeError as jde:
                        raise MalformedModelOutputError(f"Malformed or truncated model JSON output: {jde}") from jde
                else:
                    raise MalformedModelOutputError(f"Failed parsing model JSON output: {ve}") from ve
        try:
            changes = ChangeSet.model_validate(output)
        except Exception as ve:
            raise MalformedModelOutputError(f"Model output schema validation failed: {ve}") from ve"""

old_error_handling = """                from app.services.supervisor_service import supervisor_service

                await supervisor_service.record_module_disposition(
                    db, job, module, attempt, run, "BLOCKED", reason
                )"""

new_error_handling = """                if isinstance(exc, IncompleteModelOutputError):
                    run.failure_classification = "INCOMPLETE_MODEL_OUTPUT"
                elif isinstance(exc, MalformedModelOutputError):
                    run.failure_classification = "MALFORMED_MODEL_OUTPUT"
                elif run.failure_classification is None:
                    run.failure_classification = "EXECUTION_ERROR"

                from app.services.supervisor_service import supervisor_service

                await supervisor_service.record_module_disposition(
                    db, job, module, attempt, run, "BLOCKED", reason
                )"""

if old_part in content:
    content = content.replace(old_part, new_part, 1)
    print("Replaced model validation logic successfully.")
else:
    print("Warning: old_part not found!")

if old_error_handling in content:
    content = content.replace(old_error_handling, new_error_handling, 1)
    print("Replaced error handling classification successfully.")
else:
    print("Warning: old_error_handling not found!")

target_file.write_text(content, encoding="utf-8")
print("Saved backend/app/services/phase6_service.py")

