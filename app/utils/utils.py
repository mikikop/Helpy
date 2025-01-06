import asyncio
import csv
import json
import os
from datetime import datetime

import aiohttp
import fasttext
import httpx
import pandas as pd
from dotenv import load_dotenv
from fastapi import HTTPException
from google.protobuf.message import DecodeError
from openai import OpenAI

from app.utils import gtfs_realtime_pb2

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
# Go up one level to get the parent directory
parent_dir = os.path.dirname(script_dir)
# Construct path to agency_simple.txt in the data directory
agency_file_path = os.path.join(parent_dir, 'data', 'agency_simple.txt')
# Construct path to lid.176.bin in the models directory
language_file_path = os.path.join(parent_dir, 'models', 'lid.176.bin')


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
                    "ar": "لم يتم العثور على مشغلين لهذا الخط في هذه المحطة",
                    "ru": "Операторы для этого маршрута на этой остановке не найдены"
                }.get(detected_language, "No operators found for this line at this stop")
                return {
                    'success': False,
                    'error': error_message,
                }

        # If operator_id is available, proceed with filtering and ETA calculation
        filtered_times = filter_json(times_response, stop_number, operator_id, line_number)
        lineRef = [x.get("LineRef") for x in filtered_times]
        etas = get_eta(filtered_times)

        return {
            "success": True,
            "lineRef": lineRef[0],
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


def filter_json(resp_json: json, stop_code: str, agency: str, published_line: str):
    results = []
    monitored_stop_visit = resp_json["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"]

    for element in monitored_stop_visit:
        # Check if all filter conditions are met
        if (element.get("MonitoringRef") == stop_code and
                element.get("MonitoredVehicleJourney", {}).get("PublishedLineName") == published_line and
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


async def multiple_operators_at_line(resp_json: json, stop_code: str, published_line: str) -> list:
    results = set()
    monitored_stop_visit = resp_json["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]["MonitoredStopVisit"]

    for element in monitored_stop_visit:
        # Check if all filter conditions are met
        if (element.get("MonitoringRef") == stop_code and
                element.get("MonitoredVehicleJourney", {}).get("PublishedLineName") == published_line):
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


def detect_language(text_to_detect: str):
    # Download a pre-trained language identification model
    model_path = language_file_path
    model = fasttext.load_model(model_path)

    try:
        detection = model.predict(text_to_detect)
        language = detection[0][0]  # The language code
        probability = detection[1][0]  # The probability score
        print(f"Language: {language}, Probability: {probability}")
        detected_language = language.split("__")[-1]
        return detected_language
    except Exception as e:
        print(f"Language detection error: {e}")
        return "en"  # Default to English if detection fails


async def get_lines_at_stop(stop_number: str):
    try:

        # Load GTFS files
        stops_path = os.path.join(parent_dir, 'data', 'stops.txt')
        stop_times_path = os.path.join(parent_dir, 'data', 'stop_times.txt')
        trips_path = os.path.join(parent_dir, 'data', 'trips.txt')
        routes_path = os.path.join(parent_dir, 'data', 'routes.txt')

        # Ensure files exist
        for file_path in [stops_path, stop_times_path, trips_path, routes_path]:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Missing required file: {file_path}")

        # Load CSV files
        stops = pd.read_csv(stops_path)
        stop_times = pd.read_csv(stop_times_path)
        trips = pd.read_csv(trips_path)
        routes = pd.read_csv(routes_path)

        # Clean up potential whitespace issues
        stops["stop_code"] = stops["stop_code"].astype(str).str.strip()

        # Step 1: Find the stop_id associated with the stop_number
        stop_id_series = stops[stops["stop_code"] == stop_number]["stop_id"].unique()
        if len(stop_id_series) == 0:
            raise ValueError(f"No stop_id found for stop_number: {stop_number}")
        stop_id = int(stop_id_series[0])

        # Step 2: Find trip_ids associated with the stop_id
        trip_ids = stop_times[stop_times["stop_id"] == stop_id]["trip_id"]
        if trip_ids.empty:
            raise ValueError(f"No trips found for stop_id: {stop_id}")

        # Step 3: Map trip_ids to route_ids
        route_ids = trips[trips["trip_id"].isin(trip_ids)]["route_id"].unique()
        if len(route_ids) == 0:
            raise ValueError(f"No routes found for trips at stop_id: {stop_id}")

        # Step 4: Get route details
        lines = routes[routes["route_id"].isin(route_ids)][
            ["route_id", "route_short_name", "route_long_name"]].drop_duplicates(subset=["route_short_name"])
        route_short_name_list = lines["route_short_name"].tolist()

        # If no lines are found
        if not route_short_name_list:
            raise ValueError(f"No lines found for stop_number: {stop_number}")

        print("RSSSSS", route_short_name_list)

        # Return the successful response
        return {
            "success": True,
            "stop_number": stop_number,
            "lines_list": route_short_name_list
        }

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"File error: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=f"Data error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# Processing the Special messages for developers in case of changes in routes
async def fetch_and_decode_alerts():
    """
    Fetch and decode GTFS-Realtime Service Alerts from MOT API
    """
    sm_url = os.getenv("SM_URL")
    params = {
        "Key": os.getenv("API_KEY"),
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(sm_url, params=params) as response:
            if response.status == 200:
                # Read the binary content
                binary_data = await response.read()

                try:
                    # Create a FeedMessage object
                    feed = gtfs_realtime_pb2.FeedMessage()
                    # Parse the binary data
                    feed.ParseFromString(binary_data)

                    # Convert to dictionary for easier handling
                    alerts = []
                    for entity in feed.entity:
                        if entity.HasField('alert'):
                            alert_dict = {
                                'id': entity.id,
                                'alert': {
                                    'active_period': [{
                                        'start': period.start,
                                        'end': period.end
                                    } for period in entity.alert.active_period],
                                    'informed_entity': [{
                                        'agency_id': e.agency_id if e.HasField('agency_id') else None,
                                        'route_id': e.route_id if e.HasField('route_id') else None,
                                        'stop_id': e.stop_id if e.HasField('stop_id') else None,
                                        'trip': {
                                            'trip_id': e.trip.trip_id,
                                            'route_id': e.trip.route_id,
                                            'schedule_relationship': e.trip.schedule_relationship
                                        } if e.HasField('trip') else None
                                    } for e in entity.alert.informed_entity],
                                    'cause': entity.alert.cause,
                                    'effect': entity.alert.effect,
                                    'header_text': {
                                        lang: translation.text
                                        for translation in entity.alert.header_text.translation
                                        for lang in [translation.language]
                                    },
                                    'description_text': {
                                        lang: translation.text
                                        for translation in entity.alert.description_text.translation
                                        for lang in [translation.language]
                                    }
                                }
                            }
                            alerts.append(alert_dict)
                    # print("ALERT ", alerts)
                    return alerts

                except DecodeError as e:
                    print(f"Failed to decode protobuf: {e}")
                    return None
            else:
                print(f"Request failed with status {response.status}")
                return None


async def filter_alerts(resp_list: list, lineRef: str):
    """
    Filter alerts based on the given line reference number.

    Args:
        resp_list (list): List of alert response dictionaries
        lineRef (str): Route ID to filter by

    Returns:
        list: Filtered list of alerts with relevant text information
    """
    results = []

    # Process each response in the list
    for resp in resp_list:
        # Get the alert dictionary from the response
        alert = resp.get("alert")
        if not alert:
            continue

        # Check if any informed entity matches our line reference
        informed_entities = alert.get("informed_entity", [])
        matching_entities = any(
            entity.get("route_id") == lineRef
            for entity in informed_entities
        )

        if matching_entities:
            # Create the result dictionary with Hebrew texts
            result = {
                "Header_text_he": alert["header_text"]["he"],
                "Description_text_he": alert["description_text"]["he"]
            }

            # Add non-empty English and Arabic texts if they exist
            for language in ["en", "ar"]:
                if alert["header_text"][language]:
                    result[f"Header_text_{language}"] = alert["header_text"][language]
                if alert["description_text"][language]:
                    result[f"Description_text_{language}"] = alert["description_text"][language]

            results.append(result)
    print("changes ", results)
    return results
