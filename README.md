
# Helpy

Helpy is a FastAPI-based application designed to create an AI-driven WhatsApp agent tailored for the transportation sector, focusing on bus services.
The project is based on the transportation service in Israel. You can adapt it to your country. 
It uses GTFS (General Transit Feed Specification)

There are 2 apps:
1. chat_ai_call_terminal.py : allows you to run the project in your terminal (no need of Whatsapp)
Run the code:
```bash
   poetry run python -m app.ai.chat_ai_call_terminal
   ```
2. chat_ai_call_wa: create an agent on whatsapp. For that you need to reach a phone number and connect
this number to a business whatsapp account. Then you need to connect this number to WHAPI (https://tinyurl.com/whapi)

## Features
The data provided comes directly from the transit operators, 
so errors or inaccuracies may occasionally occur. Just like when speaking with a 
real transit agent, it’s important to be clear in your requests. Sometimes, 
you might need to repeat your question more clearly or double-check the information 
provided.
The service is in 5 languages: Hebrew, English, French, Spanish and Italian.

- **WhatsApp Integration**: Enables users to interact with the agent via WhatsApp for transportation-related inquiries.
- **Whatsapp Group Interaction**: Enables users to interact with the agent via WhatsApp group, so many friends will see the 
transit information together
- **Voice Interaction**: Supports voice commands for hands-free operation. (in progress)
- **Real-time Bus Information**: Provides up-to-date details on bus schedules, routes, and delays.
Give a stop number (like on the picture - 37056) and a bus line, and it will inform you on the ETA in the next
hour.

<img src="app/assets/bus_sign.png" alt="Bus sign" width="200" height="300"/>

- **Special Messages**: Special messages provided when they exist about changes on the line.
- **Stop/Lines Information**: Provides the lines stopping at a specific stop. (for now available on the terminal version)
Ask for all the lines stopping at a specific stop number, and you'll get the entire list of the
buses stopping there.
- **AI-Powered Responses**: Utilizes artificial intelligence to offer accurate and context-aware answers.

## What you need
- The key for the Transit API of your country
- The URL to request the Transit API
- The key for Whapi third party API
- The URL to request the Whapi third party API
- The URL to download the GTFS files (I pushed only the agency_simple.txt file that is a 
simplified version of the agency.txt - but you'll need to download in the same folder routes.txt, 
stop_times.txt, stops.txt and trips.txt)
- For the language detection I used fasttext (https://fasttext.cc/docs/en/language-identification.html)
You need to download the model lid.176.bin.

## Installation

1. **Clone the Repository**:

   ```bash
   git clone https://github.com/mikikop/HelpAI.git
   cd HelpAI
   ```

2. **Install Dependencies**:

   Ensure you have Poetry installed. If not, install it using:

   ```bash
   pip install poetry
   ```

   Then, install the project dependencies with:

   ```bash
   poetry install
   ```

3. **Activate the Virtual Environment** (optional):

   Poetry automatically manages a virtual environment. To activate it:

   ```bash
   poetry shell
   ```

## Configuration

Ensure you have the necessary API keys and environment variables set up for:

- **WhatsApp API**: To handle messaging services I used the WHAPI third-party service.
- **Transportation Data API**: For accessing real-time bus information.

Create a `.env` file in the project root to store these configurations:

```env
GTFS_RT_URL=the_GTFS_URL
API_KEY=your_GTFS_key
OPENAI_API_KEY=your_openai_key
WHAPI_URL="https://gate.whapi.cloud/"
WHAPI_CHANNEL_TOKEN=your_WHAPI_TOKEN
```

## Usage

1. **Run the Application** (for the Whatsapp app):

   ```bash
   poetry run uvicorn app.api.main:app --reload
   ```

2. **Access the API Documentation**:

   Navigate to `http://127.0.0.1:8000/docs` to explore the available endpoints and test the API.

## Contributing

Contributions are welcome! Please fork the repository and create a pull request with your proposed changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For questions or support, please open an issue in this repository.

### References
For using Fasttext:
1. Joulin, A., Grave, E., Bojanowski, P., & Mikolov, T. (2016). *Bag of Tricks for Efficient Text Classification*. arXiv preprint arXiv:1607.01759.
   - [Link to the paper](https://arxiv.org/abs/1607.01759)
2. Joulin, A., Grave, E., Bojanowski, P., Douze, M., Jégou, H., & Mikolov, T. (2016). *FastText.zip: Compressing text classification models*. arXiv preprint arXiv:1612.03651.
   - [Link to the paper](https://arxiv.org/abs/1612.03651)

