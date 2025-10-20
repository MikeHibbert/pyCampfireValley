"""
Party Box storage system implementation.
"""

import asyncio
import logging
import os
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from .interfaces import IPartyBox


logger = logging.getLogger(__name__)


class FileSystemPartyBox(IPartyBox):
    """
    File system-based Party Box implementation for storing torch attachments.
    """
    
    def __init__(self, base_path: str = "./party_box"):
        """
        Initialize FileSystem Party Box.
        
        Args:
            base_path: Base directory for Party Box storage
        """
        self.base_path = Path(base_path)
        
        # Create directory structure
        self.directories = {
            "incoming": self.base_path / "incoming",
            "outgoing": self.base_path / "outgoing", 
            "quarantine": self.base_path / "quarantine",
            "attachments": self.base_path / "attachments"
        }
        
        # Create subdirectories
        for category, path in self.directories.items():
            path.mkdir(parents=True, exist_ok=True)
            
            # Create additional subdirectories for incoming/outgoing
            if category in ["incoming", "outgoing"]:
                (path / "raw").mkdir(exist_ok=True)
                (path / "processed").mkdir(exist_ok=True)
        
        logger.info(f"FileSystem Party Box initialized at: {self.base_path}")
    
    async def store_attachment(self, attachment_id: str, content: bytes) -> str:
        """Store an attachment and return its storage path"""
        try:
            # Generate file path based on attachment ID
            file_path = self.directories["attachments"] / f"{attachment_id}.bin"
            
            # Write content to file
            with open(file_path, 'wb') as f:
                f.write(content)
            
            # Create metadata file
            metadata = {
                "attachment_id": attachment_id,
                "size": len(content),
                "stored_at": datetime.utcnow().isoformat(),
                "hash": hashlib.sha256(content).hexdigest()
            }
            
            metadata_path = self.directories["attachments"] / f"{attachment_id}.meta"
            with open(metadata_path, 'w') as f:
                import json
                json.dump(metadata, f, indent=2)
            
            logger.debug(f"Stored attachment {attachment_id} ({len(content)} bytes)")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Failed to store attachment {attachment_id}: {e}")
            raise
    
    async def retrieve_attachment(self, attachment_id: str) -> Optional[bytes]:
        """Retrieve an attachment by its ID"""
        try:
            file_path = self.directories["attachments"] / f"{attachment_id}.bin"
            
            if not file_path.exists():
                logger.warning(f"Attachment {attachment_id} not found")
                return None
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            logger.debug(f"Retrieved attachment {attachment_id} ({len(content)} bytes)")
            return content
            
        except Exception as e:
            logger.error(f"Failed to retrieve attachment {attachment_id}: {e}")
            return None
    
    async def delete_attachment(self, attachment_id: str) -> bool:
        """Delete an attachment"""
        try:
            file_path = self.directories["attachments"] / f"{attachment_id}.bin"
            metadata_path = self.directories["attachments"] / f"{attachment_id}.meta"
            
            deleted = False
            
            if file_path.exists():
                file_path.unlink()
                deleted = True
            
            if metadata_path.exists():
                metadata_path.unlink()
                deleted = True
            
            if deleted:
                logger.debug(f"Deleted attachment {attachment_id}")
            else:
                logger.warning(f"Attachment {attachment_id} not found for deletion")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete attachment {attachment_id}: {e}")
            return False
    
    async def list_attachments(self, category: str = "all") -> List[str]:
        """List attachments in a category"""
        try:
            attachment_ids = []
            
            if category == "all":
                # List all attachments
                search_dirs = [self.directories["attachments"]]
            elif category in self.directories:
                # List attachments in specific category
                search_dirs = [self.directories[category]]
            else:
                logger.warning(f"Unknown category: {category}")
                return []
            
            for search_dir in search_dirs:
                if search_dir.exists():
                    for file_path in search_dir.glob("*.bin"):
                        attachment_id = file_path.stem
                        attachment_ids.append(attachment_id)
            
            logger.debug(f"Listed {len(attachment_ids)} attachments in category '{category}'")
            return attachment_ids
            
        except Exception as e:
            logger.error(f"Failed to list attachments in category {category}: {e}")
            return []
    
    async def move_to_quarantine(self, attachment_id: str) -> bool:
        """Move an attachment to quarantine"""
        try:
            source_path = self.directories["attachments"] / f"{attachment_id}.bin"
            source_meta = self.directories["attachments"] / f"{attachment_id}.meta"
            
            if not source_path.exists():
                logger.warning(f"Attachment {attachment_id} not found for quarantine")
                return False
            
            # Move to quarantine directory
            quarantine_path = self.directories["quarantine"] / f"{attachment_id}.bin"
            quarantine_meta = self.directories["quarantine"] / f"{attachment_id}.meta"
            
            source_path.rename(quarantine_path)
            
            if source_meta.exists():
                source_meta.rename(quarantine_meta)
            
            # Add quarantine metadata
            quarantine_info = {
                "quarantined_at": datetime.utcnow().isoformat(),
                "reason": "Security scan flagged content",
                "original_location": "attachments"
            }
            
            quarantine_info_path = self.directories["quarantine"] / f"{attachment_id}.quarantine"
            with open(quarantine_info_path, 'w') as f:
                import json
                json.dump(quarantine_info, f, indent=2)
            
            logger.info(f"Moved attachment {attachment_id} to quarantine")
            return True
            
        except Exception as e:
            logger.error(f"Failed to quarantine attachment {attachment_id}: {e}")
            return False
    
    async def cleanup_old_attachments(self, max_age_days: int = 30) -> int:
        """Clean up old attachments and return count of deleted items"""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
            deleted_count = 0
            
            # Check all directories for old files
            for category, directory in self.directories.items():
                if not directory.exists():
                    continue
                
                for file_path in directory.iterdir():
                    if file_path.is_file():
                        # Check file modification time
                        file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        
                        if file_mtime < cutoff_date:
                            try:
                                file_path.unlink()
                                deleted_count += 1
                                logger.debug(f"Deleted old file: {file_path}")
                            except Exception as e:
                                logger.error(f"Failed to delete old file {file_path}: {e}")
            
            logger.info(f"Cleaned up {deleted_count} old attachments (older than {max_age_days} days)")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old attachments: {e}")
            return 0
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics for the Party Box"""
        try:
            stats = {
                "base_path": str(self.base_path),
                "categories": {}
            }
            
            total_size = 0
            total_files = 0
            
            for category, directory in self.directories.items():
                if not directory.exists():
                    continue
                
                category_size = 0
                category_files = 0
                
                for file_path in directory.rglob("*"):
                    if file_path.is_file():
                        file_size = file_path.stat().st_size
                        category_size += file_size
                        category_files += 1
                
                stats["categories"][category] = {
                    "files": category_files,
                    "size_bytes": category_size,
                    "size_mb": round(category_size / (1024 * 1024), 2)
                }
                
                total_size += category_size
                total_files += category_files
            
            stats["total"] = {
                "files": total_files,
                "size_bytes": total_size,
                "size_mb": round(total_size / (1024 * 1024), 2)
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return {}
    
    def __repr__(self) -> str:
        return f"FileSystemPartyBox(base_path='{self.base_path}')"