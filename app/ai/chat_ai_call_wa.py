import asyncio
import json
import logging
import os
from dotenv import load_dotenv
from langdetect import DetectorFactory, LangDetectException
from openai import OpenAI

from app.utils.messaging import send_wait_message
from app.utils.schema import get_transit_times_function, get_lines_at_stop_function, validate_transit_times

from app.utils.utils import (get_transit_times, operatorId_to_name, get_lines_at_stop, detect_language)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

EXIT_KEYWORDS = {
    "en": ["exit", "quit", "bye", "goodbye"],
    "he": ["יציאה", "להתראות", "סיום"],
    "fr": ["sortie", "quitter", "au revoir"],
    "es": ["salir", "adiós", "salida"],
    "it": ["esci", "uscita", "arrivederci"],
    "ar": ["خروج", "إنهاء", "وداعا", "إلى اللقاء"],
    "ru": ["выход", "выходить", "пока", "до свидания"]
}

EXIT_MESSAGES = {
    "en": "Thank you for using Helpy. Goodbye!",
    "he": "תודה שהשתמשת בהלפי. להתראות!",
    "fr": "Merci d'avoir utilisé Helpy. Au revoir !",
    "es": "Gracias por usar Helpy. ¡Adiós!",
    "it": "Grazie per aver utilizzato Helpy. Arrivederci!",
    "ar": "شكرًا لاستخدامك Helpy. وداعًا!",
    "ru": "Спасибо, что используете Helpy. До свидания!"
}

# Define the initial message in multiple languages
INITIAL_MESSAGES = {
    "en": "Hello! I’m Helpy, your assistant! I’ll let you know how long it will take for your next bus/train to arrive. To do this, I need you to tell me the station number where you are (it’s written on the sign at the top of the stop). Thank you!",
    "he": "שלום! אני הלפי, העוזר שלך! אני אגיד לך כמה זמן ייקח עד להגעת התחבורה הבאה שלך. כדי לעשות זאת, אני צריך שתאמר לי את מספר התחנה (המספר כתוב בשלט בראש התחנה). תודה!",
    "fr": "Bonjour! Je suis Helpy, votre assistant! Je vais vous indiquer combien de temps il reste avant l'arrivée de votre prochain bus/train. Pour cela, j'ai besoin du numéro de l'arrêt où vous vous trouvez (il est écrit sur le panneau en haut de l'arrêt). Merci!",
    "es": "¡Hola! Soy Helpy, tu asistente. Te diré cuánto tiempo tomará para que llegue tu próximo autobús/tren. Para esto, necesito que me digas el número de estación donde estás (está escrito en el letrero en la parte superior de la parada). ¡Gracias!",
    "it": "Ciao! Sono Helpy, il tuo assistente! Ti dirò quanto tempo ci vorrà prima che arrivi il tuo prossimo autobus/treno. Per farlo, ho bisogno che mi dici il numero della stazione in cui ti trovi (è scritto sul cartello in cima alla fermata). Grazie!",
    "ar": "مرحبًا! أنا Helpy، مساعدك! سأعلمك بالوقت الذي سيستغرقه وصول الحافلة/القطار التالي. للقيام بذلك، أحتاج منك أن تخبرني برقم المحطة التي تتواجد فيها (مكتوب على اللافتة في أعلى المحطة). شكرًا!",
    "ru": "Привет! Я Helpy, ваш ассистент! Я сообщу вам, сколько времени потребуется, чтобы ваш следующий автобус/поезд прибыл. Для этого мне нужно, чтобы вы сказали мне номер станции, на которой вы находитесь (он написан на знаке в верхней части остановки). Спасибо!"
}

ETA_MESSAGES = {
    "en": "For stop {stop}, line {line} operated by {agency}, the next arrivals in the next hour will be in: {times} minutes.",
    "he": "עבור תחנה {stop}, לשעה הקרובה לקו {line} מופעל על ידי {agency}, ההגעות הבאות הן בעוד: {times} דקות.",
    "fr": "Pour l'arrêt {stop}, la ligne {line} opérée par {agency}, les prochaines arrivées dans la prochaine heure seront dans: {times} minutes.",
    "es": "Para la parada {stop}, la línea {line} operada por {agency}, las próximas llegadas en la próxima hora serán en: {times} minutos.",
    "it": "Per la fermata {stop}, la linea {line} gestita da {agency}, i prossimi arrivi nella prossima ora saranno in: {times} minuti.",
    "ar": "للمحطة {stop}، الخط {line} الذي تديره {agency}، ستصل الوافدات التالية خلال الساعة القادمة في: {times} دقيقة.",
    "ru": "Для остановки {stop}, линия {line}, обслуживаемая {agency}, следующие прибытия в течение следующего часа будут через: {times} минут."
}

LINES_AT_STOP_MSG = {
    "en": "At stop {stop}, the following bus lines stop: {lines}",
    "he": "בתחנה {stop}, הקווים הבאים של אוטובוס עוברים: {lines}",
    "fr": "A l'arrêt {stop}, les lignes suivantes de bus s'arrêtent:  {lines}",
    "es": "En la parada {stop}, pasan las siguientes líneas de autobús: {lines}",
    "it": "Alla fermata {stop}, passano le seguenti linee di autobus: {lines}",
    "ar": "في المحطة {stop}، تتوقف خطوط الحافلات التالية: {lines}",
    "ru": "На остановке {stop}, следующие автобусные линии останавливаются: {lines}"
}


async def process_successful_result(result, current_language):
    """Process successful result and handle follow-up."""

    logger.info(f"current_language: {current_language}")
    if result['etas']:
        agency_name = operatorId_to_name(agency_file_path, result['agency'])
        formatted_times = ', '.join(map(str, result['etas'][:3]))

        stop = result['stop_number']
        line = result['line_number']
        agency = f"{agency_name['hebrew_name']} / {agency_name['english_name']}"
        times = formatted_times

        try:
            eta_message = ETA_MESSAGES.get(current_language, ETA_MESSAGES["en"]).format(
                stop=stop,
                line=line,
                agency=agency,
                times=times
            )
        except KeyError as e:
            logger.error(f"KeyError during message formatting: {e}")
            logger.error(f"Current result: {result}")
            raise

        return eta_message


async def process_successful_lines_at_stop(result, current_language):
    """Process successful result and handle follow-up."""

    logger.info(f"current_language: {current_language}")

    if result['lines_list']:
        stop = result['stop_number']
        formatted_lines = ', '.join(result['lines_list'])

        try:
            lines_at_stop_message = LINES_AT_STOP_MSG.get(current_language, LINES_AT_STOP_MSG["en"]).format(
                stop=stop,
                lines=formatted_lines
            )
        except KeyError as e:
            logger.error(f"KeyError during message formatting: {e}")
            logger.error(f"Current result: {result}")
            raise

        return lines_at_stop_message


async def chat_with_ai(user_message: str, user_id: str, messages: list = None):
    """
    Main chat function with OpenAI. This function detects the language of the user's input
    and responds in the same language (fallback to English if unsupported).

    Args:
        user_message (str): The user's input message.
        messages (list): A list of messages representing the conversation so far.
        user_id (str): The user's id used to send him a wait message.

    Returns:
        dict: AI's response as a dictionary with the updated messages list.
    """

    if messages is None:
        messages = []

    # Try to get the detected language from the conversation state
    if hasattr(chat_with_ai, 'detected_language'):
        detected_language = chat_with_ai.detected_language
    else:
        if user_message.strip().isdigit():
            detected_language = "en"
        else:
            try:
                detected_language = detect_language(user_message)
                logger.info(f"Detected language: {detected_language}")
            except LangDetectException:
                detected_language = "en"
                logger.info("Language detection failed. Falling back to English.")

        # Store the detected language as a function attribute
        chat_with_ai.detected_language = detected_language

    # Log detected language
    logger.info(f"Using language: {detected_language}")

    # Case 0 : Exit by keywords in multiple languages
    # Initialize the language of communication (starting with None for detection)

    try:
        logger.info("MESSAGES BEFORE CLEANING: %s", messages)
        logger.info("USER MESSAGE: %s", user_message)

        # Clean messages - only keep messages with role and content
        clean_messages = [msg for msg in messages if msg.get('role') and msg.get('content')]
        messages = clean_messages

        logger.info("MESSAGES AFTER CLEANING: %s", messages)

        # Check for exit keywords
        if user_message.lower().strip() in EXIT_KEYWORDS.get(chat_with_ai.detected_language, EXIT_KEYWORDS["en"]):
            exit_message = EXIT_MESSAGES.get(detected_language, EXIT_MESSAGES["en"])
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
                               "4. Never call get_lines_at_stop unless explicitly asked for all lines at a stop."
                               "5. ONLY ask for the agency if multiple lines with the same number exist at the stop."
                               "6. Do not request unnecessary information."
                               "Your goal is to help users get accurate estimated arrival times efficiently and with minimal friction."
                }
            )

            # Use the detected language or fall back to English
            initial_message = INITIAL_MESSAGES.get(detected_language, INITIAL_MESSAGES["en"])
            messages.append({"role": "assistant", "content": initial_message})

        # Add the user's first input
        messages.append({"role": "user", "content": user_message.strip()})

        # Prepare functions for OpenAI
        functions = [get_transit_times_function(), get_lines_at_stop_function()]

        # Call OpenAI with function calling
        response = openai_client.chat.completions.create(
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

        # Then check for function calls
        if hasattr(response_message, 'function_call') and response_message.function_call:
            function_name = response_message.function_call.name
            function_args = json.loads(response_message.function_call.arguments)

            try:
                if function_name == "get_transit_times":
                    # Validate input and process request
                    if validate_transit_times(function_args):
                        result = await get_transit_times(
                            stop_number=function_args["stop_number"],
                            line_number=function_args["line_number"],
                            operator_id=function_args.get("agency"),
                            detected_language=chat_with_ai.detected_language
                        )
                        logger.info(f"get_transit_times response: {result}")
                        logger.info(f"chat_with_ai.detected_language: {chat_with_ai.detected_language}")
                        if result.get('success'):
                            reply_message = await process_successful_result(result, chat_with_ai.detected_language)
                            messages.append({"role": "assistant", "content": reply_message})
                        else:
                            error_message = result.get('error', "An unknown error occurred.")
                            messages.append({"role": "assistant", "content": error_message})
                    else:
                        messages.append({"role": "assistant", "content": "Invalid transit request parameters."})

                elif function_name == "get_lines_at_stop":
                    stop_number = function_args["stop_number"]
                    await send_wait_message(chat_with_ai.detected_language, user_id)
                    result = await get_lines_at_stop(stop_number)
                    logger.info(f"Detected language for message: {chat_with_ai.detected_language}")
                    if result.get('success'):
                        reply_message = await process_successful_lines_at_stop(result, chat_with_ai.detected_language)
                        messages.append({"role": "assistant", "content": reply_message})
                    else:
                        error_message = result.get('error', "An unknown error occurred.")
                        messages.append({"role": "assistant", "content": error_message})
                else:
                    raise ValueError(f"Unknown function: {function_name}")
            except Exception as e:
                logger.error(f"Error: {e}")
                messages.append({"role": "assistant", "content": f"An error occurred: {str(e)}"})
                return messages
        else:
            response_dict = {"role": response_message.role, "content": response_message.content}
            messages.append(response_dict)
        return messages
    except Exception as e:
        logger.error(f"Error: {e}")
        messages.append({"role": "assistant", "content": f"An error occurred: {str(e)}"})
    return messages
