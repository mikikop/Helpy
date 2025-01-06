# schema.py
from typing import Dict, Any
import jsonschema

from app.utils.utils import get_lines_at_stop, get_transit_times


def get_transit_times_function():
    """
    Creates a function definition for OpenAI's function calling mechanism.

    Returns:
    - A dictionary describing the function parameters
    - Used to tell the AI what information it can request
    - Matches the structure expected by OpenAI's API
    """
    return {
        "name": "get_transit_times",  # Name of the function
        "description": "Retrieve transit arrival times for a specific stop and line",
        "parameters": {
            "type": "object",  # Specifies the parameters are an object
            "properties": {
                "stop_number": {
                    "type": "string",
                    "description": "Unique identifier for the bus stop"
                },
                "line_number": {
                    "type": "string",
                    "description": "Bus line number"
                },
                "agency": {
                    "type": "string",
                    "description": "Transit agency operating the line (optional)",
                    "optional": True
                }
            },
            "required": ["stop_number", "line_number"]  # Mandatory fields
        }
    }


def validate_transit_times(input_data: Dict[str, Any]) -> bool:
    """
    Validates the transit request input against a predefined JSON schema.

    Args:
    - input_data: Dictionary of transit request parameters

    Returns:
    - Boolean indicating whether the input is valid
    """
    # Use the same schema structure for validation
    TRANSIT_REQUEST_SCHEMA = {
        "type": "object",
        "properties": {
            "stop_number": {
                "type": "string",
                "description": "Unique identifier for the bus stop"
            },
            "line_number": {
                "type": "string",
                "description": "Bus line number"
            },
            "agency": {
                "type": "string",
                "description": "Transit agency operating the line (optional)",
                "optional": True
            }
        },
        "required": ["stop_number", "line_number"]
    }

    try:
        # Validate input against the schema
        jsonschema.validate(instance=input_data, schema=TRANSIT_REQUEST_SCHEMA)
        return True
    except jsonschema.exceptions.ValidationError as e:
        print(f"Validation Error: {e}")
        return False


def get_lines_at_stop_function():
    """
    Creates a function definition for OpenAI's function calling mechanism.

    Returns:
    - A dictionary describing the function parameters
    - Used to tell the AI what information it can request
    - Matches the structure expected by OpenAI's API
    """
    return {
        "name": "get_lines_at_stop",  # Name of the function
        "description": "Only use this when specifically asked to list all lines at a stop.",
        "parameters": {
            "type": "object",  # Specifies the parameters are an object
            "properties": {
                "stop_number": {
                    "type": "string",
                    "description": "Unique identifier for the bus stop."
                }
            },
            "required": ["stop_number"]  # Mandatory fields
        }
    }


def validate_lines_at_stop(inputs):
    """
    Validates and sanitizes inputs for the `get_lines_at_stop` function.

    Args:
    - inputs (dict): Inputs from the user.

    Returns:
    - dict: Validated and sanitized inputs.
    - Raises ValueError if inputs are invalid.
    """
    # Check if the required key 'stop_number' is present
    if "stop_number" not in inputs:
        raise ValueError("Missing required parameter: 'stop_number'")

    stop_number = inputs["stop_number"]

    # Validate stop_number (e.g., it should be alphanumeric)
    if not isinstance(stop_number, str) or not stop_number.strip():
        raise ValueError(f"Invalid stop_number: {stop_number}")

    # Return sanitized inputs
    return {"stop_number": stop_number.strip()}
