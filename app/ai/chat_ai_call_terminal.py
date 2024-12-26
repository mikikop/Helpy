# to run the file run the following command : poetry run python -m app.ai.chat_ai_call_terminal
import json
import os
import asyncio
from dotenv import load_dotenv
from openai import OpenAI
from ..utils.utils import (get_transit_times, operatorId_to_name, get_user_input, detect_language, get_lines_at_stop)
from ..utils.schema import (get_transit_times_function, get_lines_at_stop_function)
from langdetect import detect, DetectorFactory

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
agency_file_path = os.path.join(parent_dir, 'data', 'agency_simple.txt')

# Ensure consistent results from langdetect
DetectorFactory.seed = 0

# Constants
TRANSLATIONS_ETA = {
    "en": "For stop {stop}, line {line} operated by {agency}, the next arrivals are in: {times} minutes.",
    "he": "עבור תחנה {stop}, קו {line} מופעל על ידי {agency}, ההגעות הבאות הן בעוד: {times} דקות.",
    "fr": "Pour l'arrêt {stop}, la ligne {line} opérée par {agency}, les prochaines arrivées sont dans : {times} minutes.",
    "es": "Para la parada {stop}, la línea {line} operada por {agency}, las próximas llegadas son en: {times} minutos.",
    "it": "Per la fermata {stop}, la linea {line} gestita da {agency}, i prossimi arrivi sono tra: {times} minuti.",
}

TRANSLATIONS_FOLLOW_UP = {
    "en": {
        "follow_up": "Would you like to check another line or another station? (yes/no): ",
        "continuation": "Let's continue checking transit times. What line or station would you like to check next?"
    },
    "he": {
        "follow_up": "האם תרצה לבדוק קו נוסף או תחנה נוספת? (כן/לא): ",
        "continuation": "בוא נמשיך לבדוק זמני נסיעה. איזה קו או תחנה תרצה לבדוק הבא?"
    },
    "fr": {
        "follow_up": "Voulez-vous vérifier une autre ligne ou une autre station ? (oui/non) : ",
        "continuation": "Continuons à vérifier les horaires. Quelle ligne ou station souhaitez-vous vérifier maintenant ?"
    },
    "es": {
        "follow_up": "¿Te gustaría verificar otra línea o otra estación? (sí/no): ",
        "continuation": "Sigamos verificando los tiempos de tránsito. ¿Qué línea o estación te gustaría verificar a continuación?"
    },
    "it": {
        "follow_up": "Vuoi controllare un'altra linea o un'altra stazione? (sì/no): ",
        "continuation": "Continuiamo a controllare i tempi di transito. Quale linea o stazione vuoi controllare dopo?"
    }
}

POSITIVE_RESPONSES = {'yes', 'y', 'oui', 'o', 'sí', 'sì', 'כן'}


async def process_operator_selection(result, function_args):
    """Handle operator selection when multiple operators are found."""
    print("AI: Multiple operators found. Please choose one of the following options:")
    for option in result['lines']:
        print(option)

    operator_choice = input("Please enter the number of your chosen operator: ")
    try:
        selected_operator_idx = int(operator_choice) - 1
        selected_operator_id = result['operator_data'][selected_operator_idx][1]
        return await get_transit_times(
            function_args['stop_number'],
            function_args['line_number'],
            selected_operator_id
        )
    except (ValueError, IndexError):
        print("Invalid choice. Please try again.")
        return result


async def process_successful_result(result, current_language, messages):
    """Process successful result and handle follow-up."""
    if result['etas']:
        agency_name = operatorId_to_name(agency_file_path, result['agency'])
        formatted_times = ', '.join(map(str, result['etas'][:3]))

        eta_message = TRANSLATIONS_ETA.get(
            current_language,
            TRANSLATIONS_ETA["en"]
        ).format(
            stop=result['stop_number'],
            line=result['line_number'],
            agency=f"{agency_name['hebrew_name']} / {agency_name['english_name']}",
            times=formatted_times
        )
        print("AI:", eta_message)

        follow_up_translations = TRANSLATIONS_FOLLOW_UP.get(
            current_language,
            TRANSLATIONS_FOLLOW_UP["en"]
        )

        follow_up = input(follow_up_translations["follow_up"])
        if follow_up.lower() in POSITIVE_RESPONSES:
            print(follow_up_translations["continuation"])
            messages.append({
                "role": "assistant",
                "content": follow_up_translations["continuation"]
            })
            return True
        elif follow_up.lower() in ['no', 'n', 'non', 'לא']:
            return False
        else:
            print("Please respond with 'yes' or 'no'.")
            return True
    else:
        print(f"AI: No upcoming arrivals found for the line {result['line_number']} and stop. Another line to check?")
        return True


async def chat_with_ai():
    """Main chat function with OpenAI."""
    current_language = None
    timeout_seconds = 30
    functions = [get_transit_times_function(), get_lines_at_stop_function()]

    messages = [{
        "role": "system",
        "content": "You are Helpy, a transit assistant. When retrieving transit times:"
                   "1. Always start by collecting the stop code. If the users enters letters, ask for numbers."
                   "2. When you get a stop number, ASK for the line number before making any function calls."
                   "3. Only after having BOTH stop number and line number, use get_transit_times."
                   "4. Never call get_lines_at_stop unless explicitly asked for all lines at a stop."
                   "5. Do not request unnecessary information."
    }]

    aiMessage_init = ("Hello! I'm Helpy, your assistant! I'll let you know how long it will take for your "
                      "next bus/train to arrive. To do this, I need you to tell me the station "
                      "number where you are (it's written on the sign at the top of the stop). Thank you!")
    messages.append({"role": "user", "content": aiMessage_init})
    print(f"AI: {aiMessage_init}")

    while True:
        user_input = await get_user_input("You: ", timeout_seconds)
        if user_input is None:
            print("AI: It seems you've been inactive. Ending the session. Goodbye!")
            break

        user_input = user_input.strip()
        if user_input.lower() in ['exit', 'quit']:
            break

        if current_language is None:
            current_language = detect_language(user_input)

        messages.append({"role": "user", "content": user_input})

        try:
            response = client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                functions=functions,
                function_call="auto"
            )

            response_message = response.choices[0].message

            # First check if there's content in the message
            if response_message.content:
                print("AI:", response_message.content)
                messages.append({
                    "role": "assistant",
                    "content": response_message.content
                })
                continue  # Continue the loop to get next user input

            # Then check for function calls
            if hasattr(response_message, 'function_call') and response_message.function_call:
                function_name = response_message.function_call.name
                function_args = json.loads(response_message.function_call.arguments)

                try:
                    if function_name == "get_transit_times":
                        result = await get_transit_times(
                            stop_number=function_args["stop_number"],
                            line_number=function_args["line_number"],
                            operator_id=function_args.get("agency"),
                            detected_language=current_language
                        )
                    elif function_name == "get_lines_at_stop":
                        stop_number = function_args["stop_number"]  # Ensure this is a dictionary
                        result = await get_lines_at_stop(stop_number)
                        print(f"For stop {stop_number}, the following lines are passing through: ")
                        print(", ".join(result))
                    else:
                        raise ValueError(f"Unknown function: {function_name}")

                    if not result.get('success') and 'lines' in result:
                        result = await process_operator_selection(result, function_args)

                    if result.get('success'):
                        should_continue = await process_successful_result(result, current_language, messages)
                        if not should_continue:
                            break
                    else:
                        print(f"AI: Error - {result.get('error', 'Unknown error occurred')}")
                except ValueError as e:
                    print(f"Error: {e}")
            else:
                print("AI:", response_message.content)
                messages.append({
                    "role": "assistant",
                    "content": response_message.content
                })

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(chat_with_ai())