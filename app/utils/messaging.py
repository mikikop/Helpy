import httpx
import os
from dotenv import load_dotenv
from openai import OpenAI
import logging

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

wait_messages = {
    "en": "Please wait a moment while I process your request.",
    "es": "Por favor, espere un momento mientras proceso su solicitud.",
    "fr": "Veuillez patienter un moment pendant que je traite votre demande.",
    "it": "Per favore, aspetti un momento mentre elaboro la sua richiesta.",
    "ru": "Пожалуйста, подождите немного, пока я обрабатываю ваш запрос.",
    "ar": "الرجاء الانتظار لحظة بينما أتعامل مع طلبك.",
    "he": "אנא המתן רגע בעוד אני מעבד את בקשתך."
}


async def generate_polite_wait_message(language: str):
    """
    Generate a polite wait message based on the user's language.
    """
    # Return the appropriate message based on the language
    message = wait_messages.get(language, wait_messages["en"])  # Default to English if language is not found
    return message


async def send_wait_message(current_language: str, user_id):
    wait_message = await generate_polite_wait_message(current_language)
    try:
        async with httpx.AsyncClient() as client:
            await send_whatsapp_message(client, recipient_id=user_id, message=wait_message)
        print(f"Wait message sent successfully to user {user_id}")
    except Exception as e:
        print(f"Error sending wait message to user {user_id}: {e}")


async def send_whatsapp_message(client: httpx.AsyncClient, recipient_id: str, message: str):
    """
    Send a message via WHAPI to the recipient.
    """
    WHAPI_CHANNEL_TOKEN = os.getenv('WHAPI_CHANNEL_TOKEN')
    WHAPI_SEND_URL = os.getenv('WHAPI_URL') + "messages/text"

    payload = {
        "typing_time": 0,
        "to": recipient_id + "@s.whatsapp.net",
        "body": message
    }
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {WHAPI_CHANNEL_TOKEN}",
        "Content-Type": "application/json",
    }
    response = await client.post(WHAPI_SEND_URL, json=payload, headers=headers)

    # Raise an error if the response fails
    response.raise_for_status()
