"""
Key Management System for CampfireValley

Implements secure key generation, storage, rotation, and digital signatures
using AES-256 encryption and RSA signatures.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import secrets
import base64

from .interfaces import IKeyManager
from .models import Torch


class CampfireKeyManager(IKeyManager):
    """
    Key Manager implementation for CampfireValley
    
    Provides:
    - AES-256 key generation and storage
    - RSA key pairs for digital signatures
    - Secure key rotation
    - Valley link key management in .secrets/valley_links.json
    """
    
    def __init__(self, valley_name: str, secrets_dir: str = ".secrets"):
        self.valley_name = valley_name
        self.secrets_dir = Path(secrets_dir)
        self.valley_links_file = self.secrets_dir / "valley_links.json"
        self.keys_file = self.secrets_dir / "keys.json"
        
        # Ensure secrets directory exists
        self.secrets_dir.mkdir(exist_ok=True)
        
        # Initialize key storage
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._load_keys()
    
    def _load_keys(self) -> None:
        """Load keys from secure storage"""
        if self.keys_file.exists():
            try:
                with open(self.keys_file, 'r') as f:
                    self._keys = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self._keys = {}
    
    def _save_keys(self) -> None:
        """Save keys to secure storage"""
        with open(self.keys_file, 'w') as f:
            json.dump(self._keys, f, indent=2)
        
        # Set restrictive permissions (owner read/write only)
        os.chmod(self.keys_file, 0o600)
    
    def _generate_aes_key(self) -> str:
        """Generate a new AES-256 key"""
        key = secrets.token_bytes(32)  # 256 bits
        return base64.b64encode(key).decode('utf-8')
    
    def _generate_rsa_key_pair(self) -> tuple[str, str]:
        """Generate RSA key pair for signatures"""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Serialize private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Serialize public key
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        return (
            base64.b64encode(private_pem).decode('utf-8'),
            base64.b64encode(public_pem).decode('utf-8')
        )
    
    async def generate_key_pair(self) -> tuple[str, str]:
        """Generate a new RSA key pair for digital signatures"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._generate_rsa_key_pair
        )
    
    async def store_key(self, key_id: str, key_data: str, key_type: str = "shared") -> bool:
        """Store a key with metadata"""
        try:
            self._keys[key_id] = {
                "key_data": key_data,
                "key_type": key_type,
                "created_at": datetime.utcnow().isoformat(),
                "valley_name": self.valley_name
            }
            self._save_keys()
            return True
        except Exception:
            return False
    
    async def retrieve_key(self, key_id: str) -> Optional[str]:
        """Retrieve a key by ID"""
        key_info = self._keys.get(key_id)
        if key_info:
            return key_info["key_data"]
        return None
    
    async def delete_key(self, key_id: str) -> bool:
        """Delete a key"""
        try:
            if key_id in self._keys:
                del self._keys[key_id]
                self._save_keys()
                return True
            return False
        except Exception:
            return False
    
    async def rotate_keys(self, community_name: str) -> bool:
        """Rotate keys for a community"""
        try:
            # Generate new shared key for community
            new_shared_key = self._generate_aes_key()
            shared_key_id = f"{community_name}_shared"
            
            # Generate new signature key pair
            private_key, public_key = await self.generate_key_pair()
            private_key_id = f"{community_name}_private"
            public_key_id = f"{community_name}_public"
            
            # Store new keys
            await self.store_key(shared_key_id, new_shared_key, "shared")
            await self.store_key(private_key_id, private_key, "private")
            await self.store_key(public_key_id, public_key, "public")
            
            # Update valley links file
            await self._update_valley_links(community_name, {
                "shared_key": new_shared_key,
                "public_key": public_key,
                "rotated_at": datetime.utcnow().isoformat()
            })
            
            return True
        except Exception:
            return False
    
    async def _update_valley_links(self, community_name: str, key_info: Dict[str, str]) -> None:
        """Update valley links file with new key information"""
        valley_links = {}
        
        if self.valley_links_file.exists():
            try:
                with open(self.valley_links_file, 'r') as f:
                    valley_links = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                valley_links = {}
        
        valley_links[community_name] = key_info
        
        with open(self.valley_links_file, 'w') as f:
            json.dump(valley_links, f, indent=2)
        
        # Set restrictive permissions
        os.chmod(self.valley_links_file, 0o600)
    
    async def sign_torch(self, torch: Torch, private_key: str) -> str:
        """Sign a torch with a private key"""
        try:
            # Decode the private key
            private_key_bytes = base64.b64decode(private_key.encode('utf-8'))
            private_key_obj = serialization.load_pem_private_key(
                private_key_bytes,
                password=None,
                backend=default_backend()
            )
            
            # Create message to sign (torch payload as JSON)
            message = json.dumps({
                "id": torch.id,
                "sender": torch.sender,
                "target": torch.target,
                "payload": torch.payload,
                "timestamp": torch.timestamp.isoformat() if torch.timestamp else None
            }, sort_keys=True).encode('utf-8')
            
            # Sign the message
            signature = private_key_obj.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return base64.b64encode(signature).decode('utf-8')
        
        except Exception:
            return ""
    
    async def verify_signature(self, torch: Torch, public_key: str) -> bool:
        """Verify a torch signature with a public key"""
        try:
            if not torch.signature:
                return False
            
            # Decode the public key
            public_key_bytes = base64.b64decode(public_key.encode('utf-8'))
            public_key_obj = serialization.load_pem_public_key(
                public_key_bytes,
                backend=default_backend()
            )
            
            # Recreate the signed message
            message = json.dumps({
                "id": torch.id,
                "sender": torch.sender,
                "target": torch.target,
                "payload": torch.payload,
                "timestamp": torch.timestamp.isoformat() if torch.timestamp else None
            }, sort_keys=True).encode('utf-8')
            
            # Decode and verify signature
            signature = base64.b64decode(torch.signature.encode('utf-8'))
            
            public_key_obj.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
        
        except Exception:
            return False
    
    async def encrypt_payload(self, payload: Dict[str, Any], shared_key: str) -> str:
        """Encrypt a payload using AES-256"""
        try:
            # Decode the shared key
            key = base64.b64decode(shared_key.encode('utf-8'))
            
            # Generate random IV
            iv = secrets.token_bytes(16)
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            
            # Prepare data for encryption
            data = json.dumps(payload).encode('utf-8')
            
            # Add PKCS7 padding
            padding_length = 16 - (len(data) % 16)
            padded_data = data + bytes([padding_length] * padding_length)
            
            # Encrypt
            encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
            
            # Combine IV and encrypted data
            result = iv + encrypted_data
            
            return base64.b64encode(result).decode('utf-8')
        
        except Exception:
            return ""
    
    async def decrypt_payload(self, encrypted_payload: str, shared_key: str) -> Optional[Dict[str, Any]]:
        """Decrypt a payload using AES-256"""
        try:
            # Decode inputs
            key = base64.b64decode(shared_key.encode('utf-8'))
            encrypted_data = base64.b64decode(encrypted_payload.encode('utf-8'))
            
            # Extract IV and ciphertext
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            
            # Decrypt
            padded_data = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove PKCS7 padding
            padding_length = padded_data[-1]
            data = padded_data[:-padding_length]
            
            # Parse JSON
            return json.loads(data.decode('utf-8'))
        
        except Exception:
            return None
    
    async def get_community_keys(self, community_name: str) -> Optional[Dict[str, str]]:
        """Get all keys for a community"""
        try:
            if self.valley_links_file.exists():
                with open(self.valley_links_file, 'r') as f:
                    valley_links = json.load(f)
                    return valley_links.get(community_name)
            return None
        except Exception:
            return None
    
    async def initialize_valley_keys(self) -> bool:
        """Initialize keys for this valley"""
        try:
            # Generate valley's own key pair
            private_key, public_key = await self.generate_key_pair()
            
            # Store valley keys
            await self.store_key(f"{self.valley_name}_private", private_key, "private")
            await self.store_key(f"{self.valley_name}_public", public_key, "public")
            
            # Generate master shared key for this valley
            master_key = self._generate_aes_key()
            await self.store_key(f"{self.valley_name}_master", master_key, "master")
            
            return True
        except Exception:
            return False