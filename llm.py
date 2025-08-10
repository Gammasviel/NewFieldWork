import openai
import httpx
from config import CONNECTION_ERROR_RETRIES
from module_logger import get_module_logger

logger = get_module_logger('llm_clients')

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
    
    def generate_response(self, prompt: str) -> str:
        content = ""
        for i in range(CONNECTION_ERROR_RETRIES):
            try:
                logger.debug(f"Attempting to generate response for model {self.name}. Try {i+1}/{CONNECTION_ERROR_RETRIES}.")
                response = self.client.chat.completions.create(model=self.model, messages=[{'role': 'user', 'content': prompt}])
                try:
                    content = response.choices[0].message.content
                    logger.info(f"Successfully received response from model {self.name}.")
                except Exception as e:
                    content = response.choices[0].finish_reason
                    logger.warning(f"Could not get message content from response for model {self.name}. Reason: {content}. Error: {e}")
                break # Success, exit loop
            except openai.APIConnectionError as e:
                logger.warning(f"APIConnectionError for model {self.name} on try {i+1}. Error: {e}")
                if i == CONNECTION_ERROR_RETRIES - 1:
                     logger.error(f"Connection failed for model {self.name} after {CONNECTION_ERROR_RETRIES} retries.")
                     return "Connection error"
            except Exception as e:
                logger.error(f"An unexpected error occurred while calling model {self.name}: {e}")
                if i == CONNECTION_ERROR_RETRIES - 1:
                    return "Unexpected error"
        
        return content

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