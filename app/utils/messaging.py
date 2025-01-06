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


async def send_whatsapp_response(client, recipient_id, ai_response):
    """
    Handle sending WhatsApp messages based on AI response content.

    Args:
        client: The HTTP client for sending messages
        recipient_id: The recipient's WhatsApp ID
        ai_response: List of message dictionaries from the AI
    """
    # Ensure we have at least one message
    if not ai_response or len(ai_response) == 0:
        logger.error("Empty AI response received")
        return

    # Get the last two messages if they exist
    last_message = ai_response[-1]["content"] if ai_response else None
    second_last_message = ai_response[-2]["content"] if len(ai_response) > 1 else None

    try:
        if second_last_message and second_last_message.startswith("WARNING"):
            # Send both the warning and the transit times
            await send_whatsapp_message(client, recipient_id, second_last_message)
            if last_message:  # Ensure there's a last message before sending
                await send_whatsapp_message(client, recipient_id, last_message)
        elif last_message:
            # No warning, just send the transit times
            await send_whatsapp_message(client, recipient_id, last_message)
        else:
            logger.error("No valid message content to send")

    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        # Optionally send an error message to the user
        await send_whatsapp_message(
            client,
            recipient_id,
            "Sorry, there was an error processing your request."
        )


async def send_whatsapp_message(client: httpx.AsyncClient, recipient_id: str, message: str):
    """
    Send a message via WHAPI to the recipient.
    """
    WHAPI_CHANNEL_TOKEN = os.getenv('WHAPI_CHANNEL_TOKEN')
    WHAPI_SEND_URL = os.getenv('WHAPI_URL') + "messages/text"

    payload = {
        "typing_time": 0,
        "to": recipient_id,
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
