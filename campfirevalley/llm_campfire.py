"""
LLM-enabled Campfire implementation using the pyCampfires framework.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Union
from campfires import LLMCamperMixin
from campfires.core.openrouter import OpenRouterConfig, ChatMessage
from campfires.core.ollama import OllamaConfig
import logging
from .campfire import Campfire
from .interfaces import IMCPBroker
from .models import Torch, CampfireConfig
from .monitoring import get_monitoring_system, LogLevel, AlertSeverity


logger = logging.getLogger(__name__)


class LLMCampfire(Campfire):
    """
    LLM-enabled Campfire that can process torches using Large Language Models.
    Extends the base CampfireValley Campfire with LLM capabilities from pyCampfires.
    """
    
    def __init__(self, config: CampfireConfig, mcp_broker: IMCPBroker, 
                 llm_config: OpenRouterConfig):
        """
        Initialize an LLM-enabled Campfire instance.
        
        Args:
            config: Campfire configuration
            mcp_broker: MCP broker for communication
            llm_config: LLM configuration (OpenRouter or Ollama)
        """
        super().__init__(config, mcp_broker)
        self.llm_config = llm_config
        self._llm_camper = None
        
        logger.info(f"LLM Campfire '{config.name}' initialized with {type(llm_config).__name__}")
    
    async def start(self) -> None:
        """Start the LLM campfire and initialize LLM camper"""
        await super().start()
        
        # Create and start LLM camper
        self._llm_camper = LLMCamper(self.llm_config)
        await self._llm_camper.start()
        
        logger.info(f"LLM Campfire '{self.config.name}' started with LLM capabilities")
    
    async def stop(self) -> None:
        """Stop the LLM campfire and cleanup LLM resources"""
        if self._llm_camper:
            await self._llm_camper.stop()
            self._llm_camper = None
        
        await super().stop()
        logger.info(f"LLM Campfire '{self.config.name}' stopped")
    
    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """Process a torch using LLM capabilities"""
        if not self._running:
            logger.warning(f"LLM Campfire '{self.config.name}' is not running, cannot process torch")
            return None
        
        logger.info(f"Processing torch {torch.torch_id} with LLM in campfire '{self.config.name}'")
        
        try:
            # Get the system prompt from configuration
            system_prompt = self.config.config.get('prompts', {}).get('system', '')
            
            # Prepare the prompt with torch data
            torch_data = torch.data.get('content', str(torch.data))
            prompt = f"{system_prompt}\n\nUser Request: {torch_data}"
            
            # Process with LLM
            response = await self.process_torch_with_llm(torch, prompt)
            
            if response:
                logger.info(f"Successfully processed torch {torch.torch_id} with LLM")
                return response
            else:
                logger.warning(f"LLM processing returned no response for torch {torch.torch_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing torch {torch.torch_id} with LLM: {e}")
            return None
    
    async def process_torch_with_llm(self, torch: Torch, prompt: str, 
                                   model: Optional[str] = None) -> Optional[Torch]:
        """
        Process a torch using LLM capabilities.
        
        Args:
            torch: The torch to process
            prompt: The prompt to send to the LLM
            model: Optional specific model to use
            
        Returns:
            Processed torch with LLM response
        """
        if not self._llm_camper:
            logger.error("LLM camper not initialized")
            return None
        
        try:
            # Prepare the prompt with torch context
            context_prompt = self._prepare_context_prompt(torch, prompt)
            
            # Process with LLM
            response = await self._llm_camper.process_with_llm(
                prompt=context_prompt,
                model=model
            )
            
            # Update torch with LLM response
            if response:
                torch.data['llm_response'] = response
                torch.data['llm_model'] = model or self.llm_config.default_model
                torch.metadata['processed_by_llm'] = True
                
                logger.info(f"Torch {torch.id} processed with LLM successfully")
                return torch
            else:
                logger.warning(f"LLM processing failed for torch {torch.id}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing torch {torch.id} with LLM: {e}")
            return None
    
    def _prepare_context_prompt(self, torch: Torch, prompt: str) -> str:
        """
        Prepare a context-aware prompt including torch information.
        
        Args:
            torch: The torch being processed
            prompt: The base prompt
            
        Returns:
            Enhanced prompt with context
        """
        context = f"""
Context Information:
- Torch ID: {torch.id}
- Source: {torch.source}
- Destination: {torch.destination}
- Data Keys: {list(torch.data.keys()) if torch.data else 'None'}

User Request:
{prompt}

Please process this request considering the torch context above.
"""
        return context.strip()


class LLMCamper(LLMCamperMixin):
    """
    LLM Camper implementation using the pyCampfires LLMCamperMixin.
    """
    
    def __init__(self, llm_config: OpenRouterConfig):
        """
        Initialize LLM Camper.
        
        Args:
            llm_config: LLM configuration
        """
        super().__init__()
        self.llm_config = llm_config
        self._initialized = False
    
    async def start(self) -> None:
        """Start the LLM camper"""
        if self._initialized:
            return
        
        # Initialize LLM connection based on config type
        if isinstance(self.llm_config, OpenRouterConfig):
            await self._initialize_openrouter()
        elif isinstance(self.llm_config, OllamaConfig):
            await self._initialize_ollama()
        else:
            raise ValueError(f"Unsupported LLM config type: {type(self.llm_config)}")
        
        self._initialized = True
        logger.info("LLM Camper started successfully")
    
    async def stop(self) -> None:
        """Stop the LLM camper"""
        if not self._initialized:
            return
        
        # Cleanup LLM resources
        await self._cleanup_llm_resources()
        self._initialized = False
        logger.info("LLM Camper stopped")
    
    async def process_with_llm(self, prompt: str, model: Optional[str] = None) -> Optional[str]:
        """
        Process a prompt with the configured LLM.
        
        Args:
            prompt: The prompt to process
            model: Optional specific model to use
            
        Returns:
            LLM response or None if failed
        """
        if not self._initialized:
            logger.error("LLM Camper not initialized")
            return None
        
        # Check if using demo/placeholder API key
        if self.llm_config.api_key == 'demo_key_placeholder':
            logger.info("Using demo mode - returning mock response")
            return self._generate_mock_response(prompt)
        
        try:
            # Create chat messages for the LLM
            messages = [ChatMessage(role="user", content=prompt)]
            
            # Use the LLMCamperMixin functionality
            response = await self.llm_chat(
                messages=messages,
                model=model or self.llm_config.default_model
            )
            
            # Extract the content from the response
            if response and hasattr(response, 'choices') and response.choices:
                # choices is a List[Dict[str, Any]], so access the first choice as a dict
                first_choice = response.choices[0]
                if isinstance(first_choice, dict) and 'message' in first_choice:
                    return first_choice['message'].get('content', '')
                elif hasattr(first_choice, 'message'):
                    return first_choice.message.content
            return None
            
        except Exception as e:
            logger.error(f"LLM processing failed: {e}")
            return None
    
    def _generate_mock_response(self, prompt: str) -> str:
        """Generate a mock response for demo purposes."""
        if "marketing" in prompt.lower() or "strategy" in prompt.lower():
            return """
            **Marketing Strategy Analysis for E-commerce Innovation**
            
            Based on the current market trends and consumer behavior, here's a comprehensive marketing strategy:
            
            1. **Target Audience**: Tech-savvy millennials and Gen Z consumers who value convenience and innovation
            2. **Value Proposition**: Revolutionary e-commerce experience with AI-powered personalization
            3. **Key Channels**: Social media marketing, influencer partnerships, content marketing
            4. **Competitive Advantage**: Unique user experience and advanced recommendation engine
            5. **Launch Strategy**: Phased rollout starting with beta testing and early adopters
            
            This strategy focuses on building brand awareness while establishing market presence in the competitive e-commerce landscape.
            """
        else:
            return f"Mock response for: {prompt[:100]}..."
    
    async def _initialize_openrouter(self) -> None:
        """Initialize OpenRouter connection"""
        # Create OpenRouterConfig object
        config = OpenRouterConfig(
            api_key=self.llm_config.api_key,
            default_model=self.llm_config.default_model,
            max_tokens=getattr(self.llm_config, 'max_tokens', 1000),
            temperature=getattr(self.llm_config, 'temperature', 0.7)
        )
        
        # Setup LLM connection using the config
        self.setup_llm(config=config)
        logger.info("OpenRouter LLM initialized")

    async def _initialize_ollama(self) -> None:
        """Initialize Ollama connection"""
        # Create OllamaConfig object
        config = OllamaConfig(
            base_url=self.llm_config.base_url,
            default_model=self.llm_config.default_model
        )
        
        # Setup LLM connection using the config
        self.setup_llm(config=config)
        logger.info("Ollama LLM initialized")
    
    async def _cleanup_llm_resources(self) -> None:
        """Cleanup LLM resources"""
        # No explicit cleanup needed for LLMCamperMixin
        logger.info("LLM resources cleaned up")


# Factory functions for creating LLM campfires
def create_openrouter_campfire(config: CampfireConfig, mcp_broker: IMCPBroker,
                              api_key: str, default_model: str = "openai/gpt-3.5-turbo") -> LLMCampfire:
    """
    Create an LLM campfire using OpenRouter.
    
    Args:
        config: Campfire configuration
        mcp_broker: MCP broker
        api_key: OpenRouter API key
        default_model: Default model to use
        
    Returns:
        Configured LLM campfire
    """
    llm_config = OpenRouterConfig(
        api_key=api_key,
        default_model=default_model
    )
    return LLMCampfire(config, mcp_broker, llm_config)


def create_ollama_campfire(config: CampfireConfig, mcp_broker: IMCPBroker,
                          base_url: str = "http://localhost:11434", 
                          default_model: str = "llama2") -> LLMCampfire:
    """
    Create an LLM campfire using Ollama.
    
    Args:
        config: Campfire configuration
        mcp_broker: MCP broker
        base_url: Ollama server base URL
        default_model: Default model to use
        
    Returns:
        Configured LLM campfire
    """
    llm_config = OllamaConfig(
        base_url=base_url,
        default_model=default_model
    )
    return LLMCampfire(config, mcp_broker, llm_config)