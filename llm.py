
import openai
import httpx
from config import CONNECTION_ERROR_RETRIES

class LLMClient:
    clients: list[openai.OpenAI] = []
    
    def __init__(self, model: str, base_url: str, api_keys: list[str], proxy: str):
        self.clients = [
            self.create_client(base_url, api_key, proxy)
            for api_key in api_keys
        ]
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
        return self.clients[self.index]
    
    def generate_response(self, prompt: str) -> str:
        for _ in range(CONNECTION_ERROR_RETRIES):
            try:
                response = self.client.chat.completions.create(model=self.model, messages=[{'role': 'user', 'content': prompt}])
                break
            except openai.APIConnectionError:
                pass
        else:
            return "Connection error"
        
        try:
            content = response.choices[0].message.content
        except:
            content = response.choices[0].finish_reason
            
        return content

class Clients:
    clients: dict[int: LLMClient] = {}
    
    def __init__(self, models: list[dict] = None):
        if not models is None:
            self.create_clients(models)
    
    def create_clients(self, models: list[dict]):
        for model in models:
            self.create_client(**model)
    
    def create_client(self, id: int, model: str, base_url: str, api_keys: list[str], proxy: str):
        self.clients[id] = LLMClient(model, base_url, api_keys, proxy)
    
    def generate_response(self, prompt: str, id: int) -> str:
        return self.clients[id].generate_response(prompt)
    
    def generate_responses(self, prompt: str, exclusions: list[int]) -> dict[int: str]:
        responses = {}
        for i in self.clients:
            if i not in exclusions:
                responses[i] = self.generate_response(prompt, i)
        
clients = Clients()