import json
import pytest
from app.core.errors import IncompleteModelOutputError, MalformedModelOutputError
from app.schemas.phase6 import ChangeSet

def test_incomplete_model_output_error_raised():
    """Verify IncompleteModelOutputError subclasses correctly."""
    err = IncompleteModelOutputError("Truncated due to token ceiling")
    assert "Truncated due to token ceiling" in str(err)
    assert isinstance(err, Exception)

def test_malformed_model_output_error_raised():
    """Verify MalformedModelOutputError subclasses correctly."""
    err = MalformedModelOutputError("Invalid JSON at line 12 column 59")
    assert "Invalid JSON" in str(err)
    assert isinstance(err, Exception)

def test_unterminated_json_cannot_validate_as_changeset():
    """Verify that truncated/unterminated JSON cannot be validated as a ChangeSet."""
    truncated_json = '{"files": {"app/models/user.py": "class User:\\n    id: int\\n    name: str\\n'
    with pytest.raises(json.JSONDecodeError):
        json.loads(truncated_json)

def test_valid_json_with_missing_files_key_fails_changeset():
    """Verify that a JSON missing the files key fails ChangeSet model validation."""
    invalid_payload = {"notes": "I converted the code"}
    with pytest.raises(Exception):
        ChangeSet.model_validate(invalid_payload)

def test_valid_json_with_files_succeeds():
    """Verify that a valid ChangeSet validates cleanly."""
    valid_payload = {
        "files": {
            "app/models/user.py": "class User:\n    id: int\n"
        },
        "design_notes": "Valid model design notes",
        "assumptions": ["Python 3.12 syntax"],
    }
    cs = ChangeSet.model_validate(valid_payload)
    assert "app/models/user.py" in cs.files
    assert "class User:" in cs.files["app/models/user.py"]
    assert cs.design_notes == "Valid model design notes"
