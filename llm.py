import openai
import httpx
import ast  # Import the Abstract Syntax Tree module for safe literal evaluation
from config import CONNECTION_ERROR_RETRIES
import logging

logger = logging.getLogger('llm_clients')

class LLMClient:
    clients: list[openai.OpenAI] = []
    
    def __init__(self, name: str, model: str, base_url: str, api_keys: list[str], proxy: str):
        self.clients = [
            self.create_client(base_url, api_key, proxy)
            for api_key in api_keys
        ]
        self.name = name
        self.model = model
        self.index = -1
        
    def create_client(self, base_url: str, api_key: str, proxy: str) -> openai.OpenAI:
        return openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=httpx.Client(proxy = proxy if proxy else None)
        )
    
    @property
    def client(self) -> openai.OpenAI:
        self.index = (self.index + 1) % len(self.clients)
        logger.debug(f"Using API key index {self.index} for model {self.name}.")
        return self.clients[self.index]

    def _parse_detailed_error(self, e: openai.APIError) -> str:
        """
        Safely parses the detailed error message from an OpenAI APIError.
        This handles string formats like "Error code: 400 - {'error': ...}".
        It uses ast.literal_eval for safely parsing Python dicts from strings.
        """
        # First, try the modern, preferred way: the .body attribute
        if e.body and isinstance(e.body, dict) and 'error' in e.body:
            return e.body['error'].get('message', str(e))
        
        # If .body is not available, parse the raw e.message string
        message_str = str(e.message)
        try:
            # Find the start of the dictionary (the first '{')
            brace_index = message_str.find('{')
            if brace_index != -1:
                # Extract the dictionary part of the string
                dict_string = message_str[brace_index:]
                # Use ast.literal_eval, which is safe and handles single quotes
                error_data = ast.literal_eval(dict_string)
                if isinstance(error_data, dict) and 'error' in error_data:
                     # Use .get() for safe access
                     return error_data.get('error', {}).get('message', message_str)
        except (ValueError, SyntaxError, TypeError, KeyError) as parse_error:
            # If parsing fails for any reason, log it and return the original message
            logger.warning(f"Could not parse detailed error from message string. Error: {parse_error}. Original: '{message_str}'")
        
        return message_str # Ultimate fallback

    def generate_response(self, prompt: str) -> str:
        response = None
        # Requirement 1: Retry APIConnectionError up to CONNECTION_ERROR_RETRIES times
        for i in range(CONNECTION_ERROR_RETRIES):
            try:
                logger.debug(f"Attempting to generate response for model {self.name}. Try {i+1}/{CONNECTION_ERROR_RETRIES}.")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{'role': 'user', 'content': prompt}]
                )
                break  # Success, exit the retry loop

            except openai.APIConnectionError as e:
                logger.warning(f"APIConnectionError for model {self.name} on try {i+1}. Error: {e}")
                if i == CONNECTION_ERROR_RETRIES - 1:
                    logger.error(f"Connection finally failed for model {self.name} after {CONNECTION_ERROR_RETRIES} retries.")
                    return "Connection error"
                # Continue to the next iteration to retry
            
            # Requirement 2 & 4: Handle fatal (non-retryable) API errors
            except (openai.InternalServerError, openai.BadRequestError) as e:
                detailed_message = self._parse_detailed_error(e)
                logger.error(f"Fatal API Error for model {self.name} (BadRequest/InternalServer): {detailed_message}")
                return f"API Error: {detailed_message}" # Exit immediately, do not retry
            
            except openai.APIError as e: # Catch any other OpenAI API errors
                detailed_message = self._parse_detailed_error(e)
                logger.error(f"Unhandled API Error for model {self.name}: {detailed_message}")
                return f"API Error: {detailed_message}" # Exit immediately, do not retry

            except Exception as e:
                logger.critical(f"An unexpected non-API error occurred for model {self.name}: {e}", exc_info=True)
                return "Unexpected client error" # Exit immediately

        if response is None:
            return "Failed to get response"

        # Requirement 3: Handle unpacking response and fallback to finish_reason
        try:
            if response.choices:
                message = response.choices[0].message
                if message and message.content is not None:
                    content = message.content
                    logger.info(f"Successfully received response content from model {self.name}.")
                else:
                    content = response.choices[0].finish_reason
                    logger.warning(f"Response content was None for model {self.name}. Fallback to finish_reason: '{content}'")
            else:
                content = "No choices in response"
                logger.error(f"Response from model {self.name} contained no choices.")

        except (AttributeError, IndexError, TypeError, KeyError) as e:
            logger.warning(f"Could not extract message content for model {self.name} due to {type(e).__name__}. Fallback to finish_reason.")
            try:
                content = response.choices[0].finish_reason
            except Exception as final_e:
                logger.error(f"Critical Parsing Failure: Could not even get finish_reason for model {self.name}. Error: {final_e}")
                content = "Response parsing failed completely"
            
        return content

# The 'Clients' class below remains unchanged.

class Clients:
    clients: dict[int: LLMClient] = {}
    
    def __init__(self, models: list[dict] = None):
        if not models is None:
            self.create_clients(models)
    
    def create_clients(self, models: list[dict]):
        logger.info(f"Creating/updating a total of {len(models)} LLM clients.")
        for model in models:
            self.create_client(**model)
    
    def create_client(self, id: int, name: str, model: str, base_url: str, api_keys: list[str], proxy: str):
        logger.info(f"Initializing client for model '{name}' (ID: {id}) with {len(api_keys)} API key(s).")
        self.clients[id] = LLMClient(name, model, base_url, api_keys, proxy)
    
    def generate_response(self, prompt: str, id: int) -> str:
        return self.clients[id].generate_response(prompt)
    
    def generate_responses(self, prompt: str, exclusions: list[int]) -> dict[int: str]:
        responses = {}
        target_clients = [c for i, c in self.clients.items() if i not in exclusions]
        logger.info(f"Generating responses from {len(target_clients)} models, excluding IDs: {exclusions}.")
        for i in self.clients:
            if i not in exclusions:
                responses[i] = self.generate_response(prompt, i)
        
        return responses
        
clients = Clients()