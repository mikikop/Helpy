import asyncio
import csv
import json
import os
from datetime import datetime
from langdetect import detect
import pandas as pd
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
# Go up one level to get the parent directory
parent_dir = os.path.dirname(script_dir)
# Construct path to agency_simple.txt in the data directory
agency_file_path = os.path.join(parent_dir, 'data', 'agency_simple.txt')


async def get_transit_times(stop_number: str, line_number: str, operator_id: str = None,
                                  detected_language: str = None):
    """
    Async function to process transit requests using utils functions.

    Args:
        stop_number (str): Bus stop identifier
        line_number (str): Bus line number
        operator_id (str): Optional; Transit operator ID.
        detected_language(str): Optional; Language used bby the user to reply to him

    Returns:
        Dict: Processing result with ETAs, or operator options if clarification is needed.
    """
    try:

        # Fetch times from GTFS-RT API
        times_response = await get_times(stop_number)

        if not operator_id:
            # Check for multiple operators
            multiple_operators_for_line = await multiple_operators_at_line(times_response, stop_number, line_number)

            if len(multiple_operators_for_line) > 1:

                # Prepare options for the user
                operator_options = []
                for idx, (line, op_id) in enumerate(multiple_operators_for_line, start=1):
                    operator_info = operatorId_to_name(agency_file_path, op_id)
                    hebrew_name = operator_info['hebrew_name']
                    english_name = operator_info['english_name']
                    operator_options.append(
                        f"{idx}. {hebrew_name} / {english_name}"
                    )

                # Return options for user selection
                return {
                    'success': False,
                    'error': "Multiple operators found. Please specify the line's company.",
                    'lines': operator_options,
                    'operator_data': multiple_operators_for_line  # Include operator details for retrying
                }

            elif len(multiple_operators_for_line) == 1:
                operator_id = multiple_operators_for_line[0][1]  # Get the single operator ID
            else:
                error_message = {
                    "en": "No operators found for this line at this stop",
                    "fr": "Aucun opérateur trouvé pour cette ligne à cet arrêt.",
                    "he": "לא נמצאו מפעילים עבור הקו הזה בתחנה הזו.",
                    "es": "No se encontraron operadores para esta línea en esta parada.",
                    "it": "Nessun operatore trovato per questa linea a questa fermata.",
                }.get(detected_language, "No operators found for this line at this stop")
                return {
                    'success': False,
                    'error': error_message,
                }

        # If operator_id is available, proceed with filtering and ETA calculation
        filtered_times = filter_json(times_response, stop_number, operator_id, line_number)
        etas = get_eta(filtered_times)

        return {
            "success": True,
            "stop_number": stop_number,
            "line_number": line_number,
            "agency": operator_id,
            "etas": etas
        }

    except Exception as e:
        print(f"Error processing transit request: {e}")
        return {
            "error": str(e),
            "success": False
        }


async def get_times(current_stop_code: str, time_interval: str = "PT1H"):
    """
        Query the GTFS-RT API with the provided parameters.
        """
    GTFS_RT_URL = os.getenv("GTFS_RT_URL")
    API_KEY = os.getenv("API_KEY")
    if not GTFS_RT_URL or not API_KEY:
        raise ValueError("GTFS_RT_URL or API_KEY is not defined.")

    # Build the request parameters dynamically
    params = {
        "Key": API_KEY,
        "MonitoringRef": current_stop_code,
        "PreviewInterval": time_interval,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(GTFS_RT_URL, params=params)
        response.raise_for_status()

        # Pretty-print the response JSON with indentation
        # print(json.dumps(response.json(), indent=4))

        return response.json()


def filter_json(resp_json: json, stop_code: str, agency: str, publishedLine: str):
    results = []
    monitored_stop_visit = resp_json["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"]

    for element in monitored_stop_visit:
        # Check if all filter conditions are met
        if (element.get("MonitoringRef") == stop_code and
                element.get("MonitoredVehicleJourney", {}).get("PublishedLineName") == publishedLine and
                element.get("MonitoredVehicleJourney", {}).get("OperatorRef") == agency):
            # Extract relevant information
            vehicle_journey = element["MonitoredVehicleJourney"]
            monitored_call = vehicle_journey.get("MonitoredCall", {})

            result = {
                "MonitoringRef": element["MonitoringRef"],
                "LineRef": vehicle_journey.get("LineRef"),
                "DirectionRef": vehicle_journey.get("DirectionRef"),
                "PublishedLineName": vehicle_journey.get("PublishedLineName"),
                "OperatorRef": vehicle_journey.get("OperatorRef"),
                "ExpectedArrivalTime": monitored_call.get("ExpectedArrivalTime")
            }
            results.append(result)
    print(results)
    return results


async def multiple_operators_at_line(resp_json: json, stop_code: str, publishedLine: str) -> list:
    results = set()
    monitored_stop_visit = resp_json["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"]

    for element in monitored_stop_visit:
        # Check if all filter conditions are met
        if (element.get("MonitoringRef") == stop_code and
                element.get("MonitoredVehicleJourney", {}).get("PublishedLineName") == publishedLine):
            results.add((element["MonitoredVehicleJourney"].get("PublishedLineName"),
                         element["MonitoredVehicleJourney"].get("OperatorRef")))
    return list(results)


def get_eta(res: list):
    eta_res = []
    now = datetime.now()
    for element in res:
        arrival_time = datetime.fromisoformat(element["ExpectedArrivalTime"][:-6])  # Remove timezone
        delta = (arrival_time - now).total_seconds()
        eta_res.append(int(delta // 60) if delta > 0 else None)
    # print(eta_res)
    return eta_res


def operatorId_to_name(file_name, operator_id):
    operator_dict = {}
    try:
        with open(file_name, 'r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['agency_id'] == operator_id:
                    operator_dict['hebrew_name'] = row['agency_name']
                    operator_dict['english_name'] = row['agency_english_name']
    except FileNotFoundError:
        print("Agency file not found.")
    except Exception as e:
        print(f"Error reading agency file: {e}")
    return operator_dict


async def get_user_input(prompt, timeout):
    """
    Asks for user input with a timeout.

    Args:
        prompt (str): The prompt message for input.
        timeout (int): Timeout duration in seconds.

    Returns:
        str: User input or None if timed out.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(input, prompt), timeout)
    except asyncio.TimeoutError:
        return None


# Language detection function
def detect_language(text):
    try:
        # Only detect language if the input has valid content
        if not text.strip():
            return None  # Return None for empty input, which avoids detecting language
        language = detect(text)
        return language
    except Exception as e:
        # print(f"Language detection error: {e}")
        return "en"  # Default to English if detection fails


async def get_lines_at_stop(stop_number: str):

    # Load GTFS files
    stops = pd.read_csv(os.path.join(parent_dir, 'data', 'stops.txt'))
    stop_times = pd.read_csv(os.path.join(parent_dir, 'data', 'stop_times.txt'))
    trips = pd.read_csv(os.path.join(parent_dir, 'data', 'trips.txt'))
    routes = pd.read_csv(os.path.join(parent_dir, 'data', 'routes.txt'))

    # Clean up potential whitespace issues
    stops["stop_code"] = stops["stop_code"].astype(str).str.strip()

    # Step 1: Find the stop_id associated with the stop_number
    stop_id = int(stops[stops["stop_code"] == stop_number]["stop_id"].unique()[0])
    # print(f"Stop_id at stop number {stop_number}: {stop_id}")

    # Step 2: Find trip_ids associated with the stop_id
    trip_ids = stop_times[stop_times["stop_id"] == int(stop_id)]["trip_id"]
    # print(f"Trips at stop {stop_number}: {trip_ids}")

    # Step 3: Map trip_ids to route_ids
    route_ids = trips[trips["trip_id"].isin(trip_ids)]["route_id"].unique()
    # print(f"Routes serving stop {stop_number}: {route_ids}")

    # Step 4: Get route details
    lines = routes[routes["route_id"].isin(route_ids)][["route_id", "route_short_name", "route_long_name"]].drop_duplicates(subset=["route_short_name"])
    # Convert route_short_name to a list
    route_short_name_list = lines["route_short_name"].tolist()
    # print(f"Lines at stop {stop_number}:\n{route_short_name_list}")

    return route_short_name_list
