"""
LLM-enabled Campfire implementation using the pyCampfires framework.
"""

import asyncio
import logging
import os
import re
import math
from typing import Optional, List, Dict, Any, Union
from campfires import LLMCamperMixin
from campfires.core.openrouter import OpenRouterConfig, ChatMessage
from campfires.core.ollama import OllamaConfig, OllamaClient
import logging
from .campfire import Campfire
from .interfaces import IMCPBroker
from .models import Torch, CampfireConfig
from .monitoring import get_monitoring_system, LogLevel, AlertSeverity
from .zeitgeist_runtime import build_zeitgeist_context


logger = logging.getLogger(__name__)

_beliefs_collection = None


def _hash_embed(texts: List[str], dims: int = 384) -> List[List[float]]:
    vectors: List[List[float]] = []
    for t in texts:
        v = [0.0] * dims
        for token in re.findall(r"[a-zA-Z0-9']+", (t or "").lower()):
            idx = (hash(token) & 0x7FFFFFFF) % dims
            v[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        vectors.append([x / norm for x in v])
    return vectors


def _embed_texts(texts: List[str]) -> List[List[float]]:
    impl = (os.getenv("BELIEFS_EMBEDDING_IMPL") or "hash").strip().lower()
    if impl != "st":
        return _hash_embed(texts)
    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv("BELIEFS_EMBED_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)
        emb = model.encode(texts, normalize_embeddings=True)
        return [row.tolist() for row in emb]
    except Exception:
        return _hash_embed(texts)


def _get_beliefs_collection():
    global _beliefs_collection
    if _beliefs_collection is not None:
        return _beliefs_collection
    try:
        import chromadb
        embeddings_dir = os.getenv("EMBEDDINGS_DIR", "/app/data/embeddings")
        os.makedirs(embeddings_dir, exist_ok=True)
        client = chromadb.PersistentClient(path=os.path.join(embeddings_dir, "chroma"))
        _beliefs_collection = client.get_or_create_collection(name="campfirevalley_beliefs")
        return _beliefs_collection
    except Exception:
        _beliefs_collection = False
        return _beliefs_collection


def _get_beliefs_for(campfire_name: str, query: str, k: int = 5) -> List[str]:
    collection = _get_beliefs_collection()
    if not collection or not campfire_name or not query:
        return []
    try:
        qemb = _embed_texts([query])[0]
        result = collection.query(
            query_embeddings=[qemb],
            n_results=k,
            where={"campfire": campfire_name},
            include=["documents"]
        )
        docs = (result or {}).get("documents") or []
        if docs and isinstance(docs[0], list):
            return [d for d in docs[0] if isinstance(d, str)]
        return []
    except Exception:
        return []


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
            llm_block = (self.config.config or {}).get("llm") or {}
            llm_provider = (llm_block.get("provider") or "").strip().lower()
            selected_model = (llm_block.get("model") or "").strip() or None
            
            # Prepare the prompt with torch data (prefer 'content' or 'text')
            torch_data = torch.data.get('content') or torch.data.get('text') or str(torch.data)
            beliefs = _get_beliefs_for(self.config.name, torch_data, k=5)
            rag_docs = []
            try:
                rag_block = (self.config.config or {}).get("rag", {})
                if isinstance(rag_block, dict):
                    rag_docs = rag_block.get("documents") or []
            except Exception:
                rag_docs = []
            if not isinstance(rag_docs, list):
                rag_docs = []
            rag_docs = [d for d in rag_docs if isinstance(d, str) and d.strip()][:5]
            belief_prefix = ""
            if beliefs:
                belief_lines = "\n".join([f"- {b}" for b in beliefs])
                belief_prefix = f"You remember:\n{belief_lines}\n\n"
            rag_prefix = ""
            if rag_docs:
                rag_lines = "\n\n".join(rag_docs)
                rag_prefix = f"Reference:\n{rag_lines}\n\n"
            tools_block = (self.config.config or {}).get("tools") or {}
            zeit = tools_block.get("zeitgeist") or {}
            zeit_feats = []
            if zeit.get("enabled"):
                if zeit.get("web_search"):
                    zeit_feats.append("web_search")
                if zeit.get("image_ocr"):
                    zeit_feats.append("image_ocr")
            zeit_cap = ""
            if zeit_feats:
                zeit_cap = f"External tools available via Zeitgeist: {', '.join(zeit_feats)}.\n"
            zeit_context = ""
            try:
                zeit_cfg = dict(zeit) if isinstance(zeit, dict) else {}
                if zeit_cfg.get("image_ocr") and llm_provider == "ollama" and selected_model:
                    zeit_cfg["ollama_model"] = selected_model
                    zeit_cfg["ollama_host"] = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
                zeit_context = await build_zeitgeist_context(torch_data, zeit_cfg)
            except Exception:
                zeit_context = ""
            if zeit_context:
                zeit_cap = (zeit_cap + "\n") if zeit_cap else ""
                zeit_cap = zeit_cap + "If Zeitgeist context is present, treat it as the source of truth and do not invent facts.\n"
            prompt = f"{belief_prefix}{rag_prefix}{zeit_cap}{zeit_context}{system_prompt}\n\nUser Request: {torch_data}"
            
            # Process with LLM
            response = await self.process_torch_with_llm(torch, prompt, model=selected_model)
            
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
            response = await self._maybe_run_zeitgeist_tools(torch, prompt, response, model=model)
            
            # Update torch with LLM response
            if response:
                torch.data['llm_response'] = response
                torch.data['llm_model'] = model or getattr(self.llm_config, 'default_model', 'llama3:latest')
                torch.metadata['processed_by_llm'] = True
                
                logger.info(f"Torch {torch.id} processed with LLM successfully")
                return torch
            else:
                logger.warning(f"LLM processing failed for torch {torch.id}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing torch {torch.id} with LLM: {e}")
            return None

    def _extract_tool_code_calls(self, text: str) -> List[Dict[str, str]]:
        if not text or not isinstance(text, str):
            return []
        m = re.search(r"```tool_code\\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if not m:
            return []
        body = (m.group(1) or "").strip()
        calls: List[Dict[str, str]] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if "web_search" in low:
                q = None
                mm = re.search(r"query\\s*=\\s*['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
                if mm:
                    q = mm.group(1)
                if q is None:
                    mm = re.search(r"web_search\\s+['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
                    if mm:
                        q = mm.group(1)
                if q is None:
                    mm = re.search(r"['\"]([^'\"]+)['\"]", line)
                    if mm:
                        q = mm.group(1)
                if q:
                    calls.append({"tool": "web_search", "arg": q})
                continue
            if "fetch_url" in low:
                u = None
                mm = re.search(r"url\\s*=\\s*['\"]([^'\"]+)['\"]", line, re.IGNORECASE)
                if mm:
                    u = mm.group(1)
                if u is None:
                    mm = re.search(r"['\"]([^'\"]+)['\"]", line)
                    if mm:
                        u = mm.group(1)
                if u:
                    calls.append({"tool": "fetch_url", "arg": u})
        return calls[:3]

    async def _maybe_run_zeitgeist_tools(self, torch: Torch, base_prompt: str, response: Optional[str], model: Optional[str] = None) -> Optional[str]:
        if not response or not isinstance(response, str):
            return response
        tools_block = (self.config.config or {}).get("tools") or {}
        zeit = tools_block.get("zeitgeist") or {}
        if not zeit.get("enabled"):
            return response
        if not zeit.get("web_search"):
            return response
        calls = self._extract_tool_code_calls(response)
        if not calls:
            return response
        out_blocks: List[str] = []
        for c in calls:
            if c.get("tool") == "web_search":
                ctx = await build_zeitgeist_context(c.get("arg") or "", {"enabled": True, "web_search": True})
                if ctx:
                    out_blocks.append(ctx.strip())
            if c.get("tool") == "fetch_url":
                ctx = await build_zeitgeist_context(c.get("arg") or "", {"enabled": True, "web_search": True})
                if ctx:
                    out_blocks.append(ctx.strip())
        if not out_blocks:
            return response
        tool_out = "\n\n".join(out_blocks)
        prompt = f"{base_prompt}\n\nZeitgeist tool output:\n{tool_out}\n\nAnswer the user request using the tool output where relevant."
        context_prompt = self._prepare_context_prompt(torch, prompt)
        try:
            return await self._llm_camper.process_with_llm(prompt=context_prompt, model=model)
        except Exception:
            return response
    
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
        
        try:
            api_key = getattr(self.llm_config, "api_key", None)
            if api_key == "demo_key_placeholder":
                return self._generate_mock_response(prompt)
        except Exception:
            pass
        
        try:
            if isinstance(self.llm_config, OpenRouterConfig):
                messages = [ChatMessage(role="user", content=prompt)]
                response = await self.llm_chat(
                    messages=messages,
                    model=model or getattr(self.llm_config, "default_model", "gemma3:4b")
                )
                if response and hasattr(response, 'choices') and response.choices:
                    first_choice = response.choices[0]
                    if isinstance(first_choice, dict) and 'message' in first_choice:
                        return first_choice['message'].get('content', '')
                    elif hasattr(first_choice, 'message'):
                        return first_choice.message.content
                return None
            elif isinstance(self.llm_config, OllamaConfig):
                client = OllamaClient(self.llm_config)
                await client.start_session()
                try:
                    try:
                        result = await client.generate(
                            prompt=prompt,
                            model=model or self.llm_config.model
                        )
                        logger.info("Ollama generate succeeded")
                        return result
                    except Exception as ge:
                        logger.warning(f"Ollama generate failed, trying chat: {ge}")
                        result = await client.chat(
                            messages=[{"role": "user", "content": prompt}],
                            model=model or self.llm_config.model
                        )
                        logger.info("Ollama chat succeeded")
                        return result
                finally:
                    await client.close_session()
            else:
                logger.error(f"Unsupported LLM client type for chat: {type(self.llm_config)}")
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
        # Create OllamaConfig object (base_url only for compatibility)
        try:
            config = OllamaConfig(base_url=self.llm_config.base_url)
        except Exception:
            # Fallback to whatever config was provided
            config = self.llm_config
        # Setup LLM connection using the config; model selection happens at call time
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
    llm_config = OllamaConfig(base_url=base_url, model=default_model)
    return LLMCampfire(config, mcp_broker, llm_config)
