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
from .hierarchical_storage import (
    HierarchicalPartyBox,
    HierarchicalStorageManager,
    StorageTier,
    StoragePolicy,
    CompressionType,
    AccessPattern,
    create_hierarchical_party_box,
    migrate_from_filesystem_party_box
)


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


class PartyBoxManager:
    """
    Manager for different Party Box implementations with migration capabilities.
    """
    
    def __init__(self):
        self.party_boxes: Dict[str, IPartyBox] = {}
        self.default_type = "filesystem"
        
    async def create_party_box(
        self,
        name: str,
        box_type: str = "filesystem",
        base_path: Optional[str] = None,
        **kwargs
    ) -> IPartyBox:
        """
        Create a Party Box instance.
        
        Args:
            name: Unique name for the Party Box
            box_type: Type of Party Box ("filesystem" or "hierarchical")
            base_path: Base path for storage
            **kwargs: Additional configuration options (e.g., policy for hierarchical)
            
        Returns:
            IPartyBox: Party Box instance
        """
        if base_path is None:
            base_path = f"./party_box_{name}"
        
        if box_type == "filesystem":
            party_box = FileSystemPartyBox(base_path)
        elif box_type == "hierarchical":
            # Extract policy from kwargs if provided
            policy = kwargs.get('policy', None)
            party_box = HierarchicalPartyBox(base_path, policy=policy)
        else:
            raise ValueError(f"Unsupported Party Box type: {box_type}")
        
        self.party_boxes[name] = party_box
        logger.info(f"Created {box_type} Party Box '{name}' at {base_path}")
        
        return party_box
    
    async def get_party_box(self, name: str) -> Optional[IPartyBox]:
        """Get a Party Box by name."""
        return self.party_boxes.get(name)
    
    async def migrate_party_box(
        self,
        source_name: str,
        target_name: str,
        target_type: str = "hierarchical",
        target_base_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Migrate data from one Party Box to another.
        
        Args:
            source_name: Name of source Party Box
            target_name: Name of target Party Box
            target_type: Type of target Party Box
            target_base_path: Base path for target Party Box
            
        Returns:
            Dict[str, Any]: Migration statistics
        """
        source_box = self.party_boxes.get(source_name)
        if not source_box:
            raise ValueError(f"Source Party Box '{source_name}' not found")
        
        # Create target Party Box
        target_box = await self.create_party_box(
            target_name,
            target_type,
            target_base_path
        )
        
        # Perform migration based on types
        if isinstance(source_box, FileSystemPartyBox) and isinstance(target_box, HierarchicalPartyBox):
            return await migrate_from_filesystem_party_box(source_box, target_box)
        else:
            # Generic migration
            return await self._generic_migrate(source_box, target_box)
    
    async def _generic_migrate(self, source: IPartyBox, target: IPartyBox) -> Dict[str, Any]:
        """Generic migration between any Party Box types."""
        
        migration_stats = {
            "migrated_count": 0,
            "failed_count": 0,
            "total_size_bytes": 0
        }
        
        # Get all attachments from source
        all_attachments = await source.list_attachments()
        
        for attachment_id in all_attachments:
            try:
                # Retrieve from source
                content = await source.retrieve_attachment(attachment_id)
                if content:
                    # Store in target
                    await target.store_attachment(attachment_id, content)
                    migration_stats["migrated_count"] += 1
                    migration_stats["total_size_bytes"] += len(content)
                else:
                    migration_stats["failed_count"] += 1
                    
            except Exception as e:
                logger.error(f"Failed to migrate attachment {attachment_id}: {e}")
                migration_stats["failed_count"] += 1
        
        logger.info(f"Generic migration completed: {migration_stats}")
        return migration_stats
    
    async def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all Party Boxes."""
        
        all_stats = {}
        for name, party_box in self.party_boxes.items():
            try:
                stats = await party_box.get_storage_stats()
                all_stats[name] = {
                    "type": type(party_box).__name__,
                    "stats": stats
                }
            except Exception as e:
                logger.error(f"Failed to get stats for Party Box '{name}': {e}")
                all_stats[name] = {
                    "type": type(party_box).__name__,
                    "error": str(e)
                }
        
        return all_stats
    
    async def optimize_all(self) -> Dict[str, Dict[str, Any]]:
        """Optimize all Party Boxes that support optimization."""
        
        optimization_results = {}
        
        for name, party_box in self.party_boxes.items():
            try:
                if hasattr(party_box, 'optimize_storage'):
                    results = await party_box.optimize_storage()
                    optimization_results[name] = {
                        "type": type(party_box).__name__,
                        "results": results
                    }
                else:
                    optimization_results[name] = {
                        "type": type(party_box).__name__,
                        "message": "Optimization not supported"
                    }
            except Exception as e:
                logger.error(f"Failed to optimize Party Box '{name}': {e}")
                optimization_results[name] = {
                    "type": type(party_box).__name__,
                    "error": str(e)
                }
        
        return optimization_results
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics."""
        
        stats = {
            "total_party_boxes": len(self.party_boxes),
            "party_boxes_by_type": {},
            "total_storage_size": 0,
            "total_attachments": 0
        }
        
        # Count by type
        for party_box in self.party_boxes.values():
            box_type = type(party_box).__name__
            stats["party_boxes_by_type"][box_type] = stats["party_boxes_by_type"].get(box_type, 0) + 1
            
            # Try to get storage stats if available
            try:
                if hasattr(party_box, 'get_storage_stats'):
                    storage_stats = await party_box.get_storage_stats()
                    if isinstance(storage_stats, dict):
                        stats["total_storage_size"] += storage_stats.get("total_size_bytes", 0)
                        stats["total_attachments"] += storage_stats.get("total_objects", 0)
            except Exception as e:
                logger.debug(f"Could not get storage stats for {box_type}: {e}")
        
        return stats

    def list_party_boxes(self) -> List[Dict[str, str]]:
        """List all registered Party Boxes."""
        
        return [
            {
                "name": name,
                "type": type(party_box).__name__,
                "base_path": getattr(party_box, 'base_path', 'unknown')
            }
            for name, party_box in self.party_boxes.items()
        ]


# Global Party Box manager instance
_party_box_manager = PartyBoxManager()


# Convenience functions
async def create_party_box(
    name: str,
    box_type: str = "filesystem",
    base_path: Optional[str] = None,
    **kwargs
) -> IPartyBox:
    """Create a Party Box using the global manager."""
    return await _party_box_manager.create_party_box(name, box_type, base_path, **kwargs)


async def get_party_box(name: str) -> Optional[IPartyBox]:
    """Get a Party Box by name using the global manager."""
    return await _party_box_manager.get_party_box(name)


async def migrate_party_box(
    source_name: str,
    target_name: str,
    target_type: str = "hierarchical",
    target_base_path: Optional[str] = None
) -> Dict[str, Any]:
    """Migrate data between Party Boxes using the global manager."""
    return await _party_box_manager.migrate_party_box(
        source_name, target_name, target_type, target_base_path
    )


def get_party_box_manager() -> PartyBoxManager:
    """Get the global Party Box manager."""
    return _party_box_manager


# Factory functions for specific Party Box types
async def create_filesystem_party_box(base_path: str = "./party_box") -> FileSystemPartyBox:
    """Create a FileSystem Party Box."""
    return FileSystemPartyBox(base_path)


async def create_hierarchical_party_box_with_policy(
    base_path: str = "./hierarchical_party_box",
    policy_name: str = "default",
    compression: CompressionType = CompressionType.LZ4,
    deduplication: bool = True,
    auto_tier: bool = True
) -> HierarchicalPartyBox:
    """Create a Hierarchical Party Box with custom policy."""
    
    party_box = await create_hierarchical_party_box(base_path)
    
    # Create custom policy if not default
    if policy_name != "default":
        custom_policy = StoragePolicy(
            name=policy_name,
            tier_rules={
                StorageTier.HOT: {
                    "max_age_days": 7,
                    "max_size_mb": 1024,
                    "access_threshold": 10
                },
                StorageTier.WARM: {
                    "max_age_days": 30,
                    "max_size_mb": 10240,
                    "access_threshold": 3
                },
                StorageTier.COLD: {
                    "max_age_days": 365,
                    "max_size_mb": 102400,
                    "access_threshold": 1
                },
                StorageTier.ARCHIVE: {
                    "max_age_days": None,
                    "max_size_mb": None,
                    "access_threshold": 0
                }
            },
            compression=compression,
            deduplication=deduplication,
            auto_tier=auto_tier
        )
        
        party_box.hsm.policies[policy_name] = custom_policy
    
    return party_box