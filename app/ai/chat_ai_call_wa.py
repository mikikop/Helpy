import logging
import os

from dotenv import load_dotenv
from langdetect import detect, DetectorFactory, LangDetectException
from openai import OpenAI

from ..utils.schema import get_transit_times_function, validate_transit_times

# Import your utility functions
from ..utils.utils import (get_transit_times, operatorId_to_name)

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

# Ensure consistent results from langdetect
DetectorFactory.seed = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def chat_with_ai(user_message: str, messages: list = None):
    """
    Main chat function with OpenAI. This function detects the language of the user's input
    and responds in the same language (fallback to English if unsupported).

    Args:
        user_message (str): The user's input message.
        messages (list): A list of messages representing the conversation so far.

    Returns:
        dict: AI's response as a dictionary with the updated messages list.
    """

    if messages is None:
        messages = []

    detected_language = None

    # Try to get the detected language from the conversation state
    if hasattr(chat_with_ai, 'detected_language'):
        detected_language = chat_with_ai.detected_language

    # If language not detected yet, detect it based on the current user message
    if detected_language is None:
        if user_message.strip().isdigit():
            detected_language = "en"
        else:
            try:
                detected_language = detect(user_message)
                logger.info(f"Detected language: {detected_language}")
            except LangDetectException:
                detected_language = "en"
                logger.info("Language detection failed. Falling back to English.")

        # Store the detected language as a function attribute
        chat_with_ai.detected_language = detected_language

    # Case 0 : Exit by keywords in multiple languages
    # Initialize the language of communication (starting with None for detection)

    EXIT_KEYWORDS = {
        "en": ["exit", "quit", "bye", "goodbye"],
        "he": ["יציאה", "להתראות", "סיום"],
        "fr": ["sortie", "quitter", "au revoir"],
        "es": ["salir", "adiós", "salida"],
        "it": ["esci", "uscita", "arrivederci"]
    }
    exit_messages = {
        "en": "Thank you for using Helpy. Goodbye!",
        "he": "תודה שהשתמשת בהלפי. להתראות!",
        "fr": "Merci d'avoir utilisé Helpy. Au revoir !",
        "es": "Gracias por usar Helpy. ¡Adiós!",
        "it": "Grazie per aver utilizzato Helpy. Arrivederci!"
    }

    try:
        logger.info("MESSAGES BEFORE CLEANING: %s", messages)
        logger.info("USER MESSAGE: %s", user_message)

        # Clean messages - only keep messages with role and content
        clean_messages = [msg for msg in messages if msg.get('role') and msg.get('content')]
        messages = clean_messages

        logger.info("MESSAGES AFTER CLEANING: %s", messages)

        # Check for exit keywords
        if user_message.lower().strip() in EXIT_KEYWORDS.get(chat_with_ai.detected_language, EXIT_KEYWORDS["en"]):
            exit_message = exit_messages.get(detected_language, exit_messages["en"])
            messages.append({"role": "assistant", "content": exit_message})
            return messages

        # Validate the user message
        if not user_message.strip():
            return [{"role": "assistant",
                     "content": "I'm sorry, I didn't understand. Could you please provide more information?"}]

        if not messages:
            # Add the system message
            messages.append(
                {
                    "role": "system",
                    "content": "You are Helpy, a transit assistant. When retrieving transit times:"
                               "1. Always start by collecting the stop code. If the users enters letters, ask for numbers."
                               "2. Then, ask for the line number. Don't say you will check the ETA, just deliver it."
                               "3. Manage the follow-up conversation. If the user enters a number you don't understand "
                               "ask him if it's a stop number or a line number. Confirm."
                               "4. ONLY ask for the agency if multiple lines with the same number exist at the stop."
                               "5. Do not request unnecessary information."
                               "Your goal is to help users get accurate estimated arrival times efficiently and with minimal friction."
                }
            )

            # Define the initial message in multiple languages
            initial_messages = {
                "en": "Hello! I’m Helpy, your assistant! I’ll let you know how long it will take for your next bus/train to arrive. To do this, I need you to tell me the station number where you are (it’s written on the sign at the top of the stop). Thank you!",
                "he": "שלום! אני הלפי, העוזר שלך! אני אגיד לך כמה זמן ייקח עד להגעת התחבורה הבאה שלך. כדי לעשות זאת, אני צריך שתאמר לי את מספר התחנה (המספר כתוב בשלט בראש התחנה). תודה!",
                "fr": "Bonjour! Je suis Helpy, votre assistant! Je vais vous indiquer combien de temps il reste avant l'arrivée de votre prochain bus/train. Pour cela, j'ai besoin du numéro de l'arrêt où vous vous trouvez (il est écrit sur le panneau en haut de l'arrêt). Merci!",
                "es": "¡Hola! Soy Helpy, tu asistente. Te diré cuánto tiempo tomará para que llegue tu próximo autobús/tren. Para esto, necesito que me digas el número de estación donde estás (está escrito en el letrero en la parte superior de la parada). ¡Gracias!",
                "it": "Ciao! Sono Helpy, il tuo assistente! Ti dirò quanto tempo ci vorrà prima che arrivi il tuo prossimo autobus/treno. Per farlo, ho bisogno che mi dici il numero della stazione in cui ti trovi (è scritto sul cartello in cima alla fermata). Grazie!"
            }

            # Use the detected language or fall back to English
            initial_message = initial_messages.get(detected_language, initial_messages["en"])

            messages.append({
                "role": "assistant",
                "content": initial_message
            })

        # Add the user's first input
        messages.append({"role": "user", "content": user_message.strip()})

        # Prepare functions for OpenAI
        functions = [get_transit_times_function()]

        # Call OpenAI with function calling
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            functions=functions,
            function_call="auto"
        )

        # Parse OpenAI's response
        response_message = response.choices[0].message

        # Convert response to dictionary (JSON-serializable)
        response_dict = {"role": response_message.role, "content": response_message.content}

        # Add AI response to conversation
        messages.append(response_dict)

        # Check if a function call is required
        if response_message.function_call:
            function_args = eval(response_message.function_call.arguments)

            # Validate input and process request
            if validate_transit_times(function_args):
                result = await get_transit_times(
                    function_args['stop_number'],
                    function_args['line_number'],
                    function_args.get('agency'),
                    chat_with_ai.detected_language
                )

                if result.get('success'):
                    agency_name = operatorId_to_name(agency_file_path, result['agency'])
                    formatted_times = ', '.join(map(str, result['etas'][:3]))
                    eta_message = {
                        "en": f"For stop {result['stop_number']}, line {result['line_number']} operated by {agency_name['english_name']}, the next arrivals in the next hour will be in: {formatted_times} minutes.",
                        "he": f"עבור תחנה {result['stop_number']} לשעה הקרובה לקו {result['line_number']} מופעל על ידי {agency_name['hebrew_name']}, ההגעות הבאות הן בעוד: {formatted_times} דקות.",
                        "fr": f"Pour l'arrêt {result['stop_number']}, la ligne {result['line_number']} opérée par {agency_name['english_name']}, les prochaines arrivées dans la prochaine heure seront dans: {formatted_times} minutes.",
                        "es": f"Para la parada {result['stop_number']}, la línea {result['line_number']} operada por {agency_name['english_name']}, las próximas llegadas en la próxima hora serán en: {formatted_times} minutos.",
                        "it": f"Per la fermata {result['stop_number']}, la linea {result['line_number']} gestita da {agency_name['english_name']}, i prossimi arrivi nella prossima ora saranno in: {formatted_times} minuti.",
                    }.get(chat_with_ai.detected_language,
                          f"For stop {result['stop_number']}, line {result['line_number']} arrivals are in: {formatted_times} minutes.")
                    messages.append({"role": "assistant", "content": eta_message})
                else:
                    error_message = result.get('error', "An unknown error occurred.")
                    messages.append({"role": "assistant", "content": error_message})
            else:
                messages.append({"role": "assistant", "content": "Invalid transit request parameters."})
        else:
            response_dict = {"role": response_message.role, "content": response_message.content}
            messages.append(response_dict)
        return messages

    except Exception as e:
        logger.error(f"Error: {e}")
        messages.append({"role": "assistant", "content": f"An error occurred: {str(e)}"})
        return messages
