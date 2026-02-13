import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Dict, Any
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from colorama import Fore, Style

logger = logging.getLogger(__name__)

def c(text: str, color: str = "") -> str:
    """Colorize text if color support is enabled."""
    if not color:
        return str(text)
    reset = getattr(Style, 'RESET_ALL', '')
    return f"{color}{text}{reset}"

# ══════════════════════════════════════════════════════════════════════════════
#  LOCAL MODEL WRAPPER (HUGGING FACE TRANSFORMERS)
# ══════════════════════════════════════════════════════════════════════════════


class LocalModel:
    """Wrapper for Hugging Face Transformers model (like Gemma)."""

    def __init__(self, model_path: str, device: str = "auto", quantize: bool = True):
        self.logger = logging.getLogger(__name__)
        self.model_path = Path(model_path)
        print(c(f"[Nexuss] Loading model from {self.model_path}...", Fore.CYAN))

        has_cuda = torch.cuda.is_available()
        if has_cuda:
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
            print(c(f"[Nexuss] GPU detected: {gpu_name} ({vram_gb} GB VRAM)", Fore.YELLOW))
        else:
            print(c("[Nexuss] No GPU detected — using CPU (slower)", Fore.YELLOW))

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)

        load_kwargs: Dict[str, Any] = {"device_map": device}

        if has_cuda and quantize:
            # 4-bit quantization: fits 2B models in ~1.2GB VRAM
            print(c("[Nexuss] Using 4-bit quantization (NF4) for speed", Fore.YELLOW))
            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
            )
        elif has_cuda:
            # float16 — native on GTX 1650+
            load_kwargs["torch_dtype"] = torch.float16
        else:
            load_kwargs["torch_dtype"] = torch.float32

        self.model = AutoModelForCausalLM.from_pretrained(self.model_path, **load_kwargs)
        self.model.eval()

        device_used = next(self.model.parameters()).device
        print(c(f"[Nexuss] Model loaded on {device_used}!", Fore.GREEN))

    def chat(
        self,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        tools: Optional[List[Any]] = None,
        stream: bool = False,
        timeout_seconds: Optional[float] = None,
    ) -> Dict:
        """
        Mimics the structure of ollama.Client.chat response.
        messages: list of dict with 'role' and 'content'.
        returns a dict with a 'message' field containing 'role' and 'content'.
        """
        chat_messages = messages or []

        # Gemma (and some other models) don't support the "system" role
        # and require strict user/assistant alternation.
        # 1) Merge system messages into the next user message.
        # 2) Collapse consecutive same-role messages.
        merged: List[Dict[str, str]] = []
        system_buf: List[str] = []
        for msg in chat_messages:
            role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if role == "system":
                system_buf.append(content)
                continue
            if role == "tool":
                role = "user"
                content = f"[Tool result] {content}"
            if system_buf and role == "user":
                content = "\n".join(system_buf) + "\n\n" + content
                system_buf.clear()
            # Collapse consecutive same-role messages
            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n" + content
            else:
                merged.append({"role": role, "content": content})
        # Flush remaining system content
        if system_buf:
            text = "\n".join(system_buf)
            if merged and merged[-1]["role"] == "user":
                merged[-1]["content"] += "\n" + text
            else:
                merged.append({"role": "user", "content": text})
        if not merged:
            merged.append({"role": "user", "content": ""})
        # Gemma requires the conversation to start with a user turn
        if merged[0]["role"] != "user":
            merged.insert(0, {"role": "user", "content": "(start)"})
        # Ensure alternation: if two same roles are adjacent, merge them
        final: List[Dict[str, str]] = [merged[0]]
        for m in merged[1:]:
            if m["role"] == final[-1]["role"]:
                final[-1]["content"] += "\n" + m["content"]
            else:
                final.append(m)

        prompt = self.tokenizer.apply_chat_template(
            final,
            tokenize=False,
            add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        gen_kwargs: Dict[str, Any] = {
            "max_new_tokens": 512,
            "temperature": 0.7,
            "do_sample": True,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if timeout_seconds is not None:
            gen_kwargs["max_time"] = timeout_seconds

        logger.info("LocalModel.chat() generating response...")
        with torch.no_grad():
            outputs = self.model.generate(**inputs, **gen_kwargs)
        logger.info("LocalModel.chat() generation complete.")

        response_text = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

        # Return a dot-accessible object that mirrors ollama's ChatResponse
        msg_obj = SimpleNamespace(role="assistant", content=response_text, tool_calls=None)
        return SimpleNamespace(message=msg_obj)