"""
Hierarchical Storage Management (HSM) system for CampfireValley Party Box.

This module provides advanced storage capabilities including:
- Multi-tier storage (hot, warm, cold, archive)
- Data deduplication and compression
- Intelligent data lifecycle management
- Storage optimization and analytics
- Distributed storage support
"""

import asyncio
import hashlib
import json
import logging
import lz4.frame
import os
import shutil
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from concurrent.futures import ThreadPoolExecutor

from .interfaces import IPartyBox


logger = logging.getLogger(__name__)


class StorageTier(Enum):
    """Storage tier levels for hierarchical storage"""
    HOT = "hot"           # Fastest access, most expensive (SSD, RAM cache)
    WARM = "warm"         # Medium access speed, medium cost (SSD)
    COLD = "cold"         # Slower access, lower cost (HDD)
    ARCHIVE = "archive"   # Slowest access, lowest cost (tape, cloud)


class CompressionType(Enum):
    """Compression algorithms supported"""
    NONE = "none"
    LZ4 = "lz4"
    GZIP = "gzip"
    ZSTD = "zstd"


class AccessPattern(Enum):
    """Data access patterns for optimization"""
    FREQUENT = "frequent"     # Accessed multiple times per day
    REGULAR = "regular"       # Accessed weekly
    OCCASIONAL = "occasional" # Accessed monthly
    RARE = "rare"            # Accessed yearly or less


@dataclass
class StoragePolicy:
    """Policy for data storage and lifecycle management"""
    name: str
    tier_rules: Dict[StorageTier, Dict[str, Any]]
    compression: CompressionType = CompressionType.LZ4
    deduplication: bool = True
    encryption: bool = True
    retention_days: Optional[int] = None
    auto_tier: bool = True
    access_pattern: AccessPattern = AccessPattern.REGULAR


@dataclass
class StorageMetadata:
    """Metadata for stored objects"""
    object_id: str
    original_size: int
    compressed_size: int
    compression_type: CompressionType
    checksum: str
    tier: StorageTier
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    is_deduplicated: bool = False
    dedup_refs: int = 1
    tags: Dict[str, str] = field(default_factory=dict)
    policy_name: str = "default"


@dataclass
class StorageStats:
    """Storage statistics and analytics"""
    total_objects: int
    total_size_bytes: int
    compressed_size_bytes: int
    compression_ratio: float
    deduplication_ratio: float
    tier_distribution: Dict[StorageTier, int]
    access_patterns: Dict[AccessPattern, int]
    storage_efficiency: float


class IStorageTierProvider(ABC):
    """Interface for storage tier providers"""
    
    @abstractmethod
    async def store(self, object_id: str, data: bytes, metadata: StorageMetadata) -> str:
        """Store data in this tier"""
        pass
    
    @abstractmethod
    async def retrieve(self, object_id: str, storage_path: str) -> Optional[bytes]:
        """Retrieve data from this tier"""
        pass
    
    @abstractmethod
    async def delete(self, object_id: str, storage_path: str) -> bool:
        """Delete data from this tier"""
        pass
    
    @abstractmethod
    async def exists(self, object_id: str, storage_path: str) -> bool:
        """Check if data exists in this tier"""
        pass
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get tier statistics"""
        pass


class FileSystemTierProvider(IStorageTierProvider):
    """File system-based storage tier provider"""
    
    def __init__(self, base_path: str, tier: StorageTier):
        self.base_path = Path(base_path)
        self.tier = tier
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for organization
        self.data_dir = self.base_path / "data"
        self.metadata_dir = self.base_path / "metadata"
        self.index_dir = self.base_path / "index"
        
        for dir_path in [self.data_dir, self.metadata_dir, self.index_dir]:
            dir_path.mkdir(exist_ok=True)
    
    async def store(self, object_id: str, data: bytes, metadata: StorageMetadata) -> str:
        """Store data in file system"""
        try:
            # Create hierarchical directory structure based on object ID
            prefix = object_id[:2]
            subdir = self.data_dir / prefix
            subdir.mkdir(exist_ok=True)
            
            # Store data
            data_path = subdir / f"{object_id}.dat"
            with open(data_path, 'wb') as f:
                f.write(data)
            
            # Store metadata
            metadata_path = self.metadata_dir / f"{object_id}.meta"
            with open(metadata_path, 'w') as f:
                json.dump({
                    'object_id': metadata.object_id,
                    'original_size': metadata.original_size,
                    'compressed_size': metadata.compressed_size,
                    'compression_type': metadata.compression_type.value,
                    'checksum': metadata.checksum,
                    'tier': metadata.tier.value,
                    'created_at': metadata.created_at.isoformat(),
                    'last_accessed': metadata.last_accessed.isoformat(),
                    'access_count': metadata.access_count,
                    'is_deduplicated': metadata.is_deduplicated,
                    'dedup_refs': metadata.dedup_refs,
                    'tags': metadata.tags,
                    'policy_name': metadata.policy_name
                }, f, indent=2)
            
            return str(data_path)
            
        except Exception as e:
            logger.error(f"Failed to store object {object_id} in {self.tier}: {e}")
            raise
    
    async def retrieve(self, object_id: str, storage_path: str) -> Optional[bytes]:
        """Retrieve data from file system"""
        try:
            data_path = Path(storage_path)
            if not data_path.exists():
                return None
            
            with open(data_path, 'rb') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Failed to retrieve object {object_id} from {self.tier}: {e}")
            return None
    
    async def delete(self, object_id: str, storage_path: str) -> bool:
        """Delete data from file system"""
        try:
            data_path = Path(storage_path)
            metadata_path = self.metadata_dir / f"{object_id}.meta"
            
            deleted = False
            if data_path.exists():
                data_path.unlink()
                deleted = True
            
            if metadata_path.exists():
                metadata_path.unlink()
                deleted = True
            
            return deleted
            
        except Exception as e:
            logger.error(f"Failed to delete object {object_id} from {self.tier}: {e}")
            return False
    
    async def exists(self, object_id: str, storage_path: str) -> bool:
        """Check if data exists in file system"""
        return Path(storage_path).exists()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get file system tier statistics"""
        try:
            total_size = 0
            file_count = 0
            
            for file_path in self.data_dir.rglob("*.dat"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            return {
                "tier": self.tier.value,
                "total_files": file_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "base_path": str(self.base_path)
            }
            
        except Exception as e:
            logger.error(f"Failed to get stats for {self.tier}: {e}")
            return {}


class CompressionManager:
    """Manages data compression and decompression"""
    
    @staticmethod
    async def compress(data: bytes, compression_type: CompressionType) -> bytes:
        """Compress data using specified algorithm"""
        if compression_type == CompressionType.NONE:
            return data
        elif compression_type == CompressionType.LZ4:
            return lz4.frame.compress(data)
        elif compression_type == CompressionType.GZIP:
            import gzip
            return gzip.compress(data)
        elif compression_type == CompressionType.ZSTD:
            try:
                import zstandard as zstd
                cctx = zstd.ZstdCompressor()
                return cctx.compress(data)
            except ImportError:
                logger.warning("zstandard not available, falling back to LZ4")
                return lz4.frame.compress(data)
        else:
            raise ValueError(f"Unsupported compression type: {compression_type}")
    
    @staticmethod
    async def decompress(data: bytes, compression_type: CompressionType) -> bytes:
        """Decompress data using specified algorithm"""
        if compression_type == CompressionType.NONE:
            return data
        elif compression_type == CompressionType.LZ4:
            return lz4.frame.decompress(data)
        elif compression_type == CompressionType.GZIP:
            import gzip
            return gzip.decompress(data)
        elif compression_type == CompressionType.ZSTD:
            try:
                import zstandard as zstd
                dctx = zstd.ZstdDecompressor()
                return dctx.decompress(data)
            except ImportError:
                logger.warning("zstandard not available, using LZ4")
                return lz4.frame.decompress(data)
        else:
            raise ValueError(f"Unsupported compression type: {compression_type}")


class DeduplicationManager:
    """Manages data deduplication"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        # Ensure the directory exists
        db_parent = Path(self.db_path).parent
        db_parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize deduplication database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dedup_index (
                    checksum TEXT PRIMARY KEY,
                    object_id TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    ref_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    async def check_duplicate(self, checksum: str) -> Optional[Tuple[str, str]]:
        """Check if data with this checksum already exists"""
        import asyncio
        
        db_path = self.db_path  # Capture the db_path for the inner function
        
        def _check_duplicate():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute(
                    "SELECT object_id, storage_path FROM dedup_index WHERE checksum = ?",
                    (checksum,)
                )
                result = cursor.fetchone()
                return result if result else None
        
        return await asyncio.to_thread(_check_duplicate)
    
    async def add_reference(self, checksum: str, object_id: str, storage_path: str) -> bool:
        """Add a reference to existing data or create new entry"""
        import asyncio
        
        db_path = self.db_path  # Capture the db_path for the inner function
        
        def _add_reference():
            with sqlite3.connect(db_path) as conn:
                # Check if checksum exists
                cursor = conn.execute(
                    "SELECT ref_count FROM dedup_index WHERE checksum = ?",
                    (checksum,)
                )
                result = cursor.fetchone()
                
                if result:
                    # Increment reference count
                    conn.execute(
                        "UPDATE dedup_index SET ref_count = ref_count + 1 WHERE checksum = ?",
                        (checksum,)
                    )
                    conn.commit()
                    return True  # Deduplicated
                else:
                    # Create new entry
                    conn.execute(
                        "INSERT INTO dedup_index (checksum, object_id, storage_path) VALUES (?, ?, ?)",
                        (checksum, object_id, storage_path)
                    )
                    conn.commit()
                    return False  # Not deduplicated
        
        return await asyncio.to_thread(_add_reference)
    
    async def remove_reference(self, checksum: str) -> bool:
        """Remove a reference and return True if this was the last reference"""
        import asyncio
        
        db_path = self.db_path  # Capture the db_path for the inner function
        
        def _remove_reference():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute(
                    "SELECT ref_count FROM dedup_index WHERE checksum = ?",
                    (checksum,)
                )
                result = cursor.fetchone()
                
                if not result:
                    return True  # Already gone
                
                ref_count = result[0]
                if ref_count <= 1:
                    # Remove entry
                    conn.execute(
                        "DELETE FROM dedup_index WHERE checksum = ?",
                        (checksum,)
                    )
                    conn.commit()
                    return True  # Last reference removed
                else:
                    # Decrement reference count
                    conn.execute(
                        "UPDATE dedup_index SET ref_count = ref_count - 1 WHERE checksum = ?",
                        (checksum,)
                    )
                    conn.commit()
                    return False  # Still has references
        
        return await asyncio.to_thread(_remove_reference)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*), SUM(ref_count) FROM dedup_index"
            )
            result = cursor.fetchone()
            
            unique_objects = result[0] if result[0] else 0
            total_references = result[1] if result[1] else 0
            
            dedup_ratio = (total_references - unique_objects) / total_references if total_references > 0 else 0
            
            return {
                "unique_objects": unique_objects,
                "total_references": total_references,
                "deduplication_ratio": round(dedup_ratio, 4),
                "space_saved_ratio": round(dedup_ratio, 4)
            }


class HierarchicalStorageManager:
    """Main hierarchical storage management system"""
    
    def __init__(self, base_path: str = "./hsm_storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.tier_providers: Dict[StorageTier, IStorageTierProvider] = {}
        self.compression_manager = CompressionManager()
        self.dedup_manager = DeduplicationManager(str(self.base_path / "dedup.db"))
        
        # Storage policies
        self.policies: Dict[str, StoragePolicy] = {}
        self.default_policy = self._create_default_policy()
        self.policies["default"] = self.default_policy
        
        # Metadata database
        self.metadata_db_path = str(self.base_path / "metadata.db")
        self._init_metadata_database()
        
        # Thread pool for I/O operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Initialize tier providers
        self._init_tier_providers()
    
    def _create_default_policy(self) -> StoragePolicy:
        """Create default storage policy"""
        return StoragePolicy(
            name="default",
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
            compression=CompressionType.LZ4,
            deduplication=True,
            auto_tier=True
        )
    
    def _init_tier_providers(self):
        """Initialize storage tier providers"""
        for tier in StorageTier:
            tier_path = self.base_path / tier.value
            self.tier_providers[tier] = FileSystemTierProvider(str(tier_path), tier)
    
    def _init_metadata_database(self):
        """Initialize metadata database"""
        with sqlite3.connect(self.metadata_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS object_metadata (
                    object_id TEXT PRIMARY KEY,
                    original_size INTEGER NOT NULL,
                    compressed_size INTEGER NOT NULL,
                    compression_type TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    last_accessed TIMESTAMP NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    is_deduplicated BOOLEAN DEFAULT FALSE,
                    dedup_refs INTEGER DEFAULT 1,
                    tags TEXT DEFAULT '{}',
                    policy_name TEXT DEFAULT 'default'
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_checksum ON object_metadata(checksum)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tier ON object_metadata(tier)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_accessed ON object_metadata(last_accessed)
            """)
            
            conn.commit()
    
    async def store_object(
        self,
        object_id: str,
        data: bytes,
        policy_name: str = "default",
        tags: Optional[Dict[str, str]] = None,
        tier: Optional[StorageTier] = None
    ) -> StorageMetadata:
        """Store an object in the hierarchical storage system"""
        
        policy = self.policies.get(policy_name, self.default_policy)
        tags = tags or {}
        
        # Calculate checksum
        checksum = hashlib.sha256(data).hexdigest()
        
        # Check for deduplication
        is_deduplicated = False
        storage_path = None
        compressed_data = data
        compression_type = CompressionType.NONE
        
        if policy.deduplication:
            existing = await self.dedup_manager.check_duplicate(checksum)
            if existing:
                # Data already exists, just add reference
                is_deduplicated = True
                storage_path = existing[1]
                await self.dedup_manager.add_reference(checksum, object_id, storage_path)
                
                # Get existing metadata for compression and tier info
                existing_metadata = await self._get_metadata(existing[0])
                if existing_metadata:
                    tier = existing_metadata.tier
                    compression_type = existing_metadata.compression_type
                    compressed_data = await self.compression_manager.compress(data, compression_type)
        
        # Determine storage tier
        if tier is None:
            tier = self._determine_initial_tier(len(data), policy)
        
        # Compress data if not deduplicated
        if not is_deduplicated:
            compression_type = policy.compression
            compressed_data = await self.compression_manager.compress(data, compression_type)
        
        # Store data if not deduplicated
        if not is_deduplicated:
            provider = self.tier_providers[tier]
            
            # Create metadata for storage
            temp_metadata = StorageMetadata(
                object_id=object_id,
                original_size=len(data),
                compressed_size=len(compressed_data),
                compression_type=compression_type,
                checksum=checksum,
                tier=tier,
                created_at=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=0,
                is_deduplicated=False,
                dedup_refs=1,
                tags=tags,
                policy_name=policy_name
            )
            
            storage_path = await provider.store(object_id, compressed_data, temp_metadata)
            
            # Add to deduplication index
            if policy.deduplication:
                await self.dedup_manager.add_reference(checksum, object_id, storage_path)
        
        # Create final metadata
        metadata = StorageMetadata(
            object_id=object_id,
            original_size=len(data),
            compressed_size=len(compressed_data),
            compression_type=compression_type,
            checksum=checksum,
            tier=tier,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
            access_count=0,
            is_deduplicated=is_deduplicated,
            dedup_refs=1,
            tags=tags,
            policy_name=policy_name
        )
        
        # Store metadata in database
        await self._store_metadata(metadata, storage_path)
        
        logger.info(f"Stored object {object_id} in {tier.value} tier (deduplicated: {is_deduplicated})")
        return metadata
    
    async def retrieve_object(self, object_id: str) -> Optional[bytes]:
        """Retrieve an object from storage"""
        
        # Get metadata
        metadata = await self._get_metadata(object_id)
        if not metadata:
            return None
        
        # Get storage path
        storage_path = await self._get_storage_path(object_id)
        if not storage_path:
            return None
        
        # Retrieve from appropriate tier
        provider = self.tier_providers[metadata.tier]
        compressed_data = await provider.retrieve(object_id, storage_path)
        
        if compressed_data is None:
            return None
        
        # Decompress data
        data = await self.compression_manager.decompress(
            compressed_data, 
            metadata.compression_type
        )
        
        # Update access statistics
        await self._update_access_stats(object_id)
        
        # Check if tier migration is needed
        if self.policies[metadata.policy_name].auto_tier:
            await self._check_tier_migration(object_id, metadata)
        
        logger.debug(f"Retrieved object {object_id} from {metadata.tier.value} tier")
        return data
    
    async def delete_object(self, object_id: str) -> bool:
        """Delete an object from storage"""
        
        # Get metadata
        metadata = await self._get_metadata(object_id)
        if not metadata:
            return False
        
        # Get storage path
        storage_path = await self._get_storage_path(object_id)
        if not storage_path:
            return False
        
        # Handle deduplication
        should_delete_data = True
        if metadata.is_deduplicated or self.policies[metadata.policy_name].deduplication:
            should_delete_data = await self.dedup_manager.remove_reference(metadata.checksum)
        
        # Delete data if this was the last reference
        if should_delete_data:
            provider = self.tier_providers[metadata.tier]
            await provider.delete(object_id, storage_path)
        
        # Remove metadata
        await self._delete_metadata(object_id)
        
        logger.info(f"Deleted object {object_id} from {metadata.tier.value} tier")
        return True
    
    async def list_objects(
        self,
        tier: Optional[StorageTier] = None,
        policy: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """List objects matching criteria"""
        
        query = "SELECT object_id FROM object_metadata WHERE 1=1"
        params = []
        
        if tier:
            query += " AND tier = ?"
            params.append(tier.value)
        
        if policy:
            query += " AND policy_name = ?"
            params.append(policy)
        
        if tags:
            for key, value in tags.items():
                query += " AND json_extract(tags, ?) = ?"
                params.extend([f"$.{key}", value])
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            cursor = conn.execute(query, params)
            return [row[0] for row in cursor.fetchall()]
    
    async def get_object_metadata(self, object_id: str) -> Optional[StorageMetadata]:
        """Get metadata for an object"""
        return await self._get_metadata(object_id)
    
    async def migrate_object(self, object_id: str, target_tier: StorageTier) -> bool:
        """Migrate an object to a different storage tier"""
        
        # Get current metadata
        metadata = await self._get_metadata(object_id)
        if not metadata or metadata.tier == target_tier:
            return False
        
        # Retrieve data from current tier
        data = await self.retrieve_object(object_id)
        if data is None:
            return False
        
        # Store in target tier
        target_provider = self.tier_providers[target_tier]
        
        # Compress for new tier if needed
        policy = self.policies[metadata.policy_name]
        compressed_data = await self.compression_manager.compress(data, policy.compression)
        
        # Update metadata
        metadata.tier = target_tier
        metadata.compressed_size = len(compressed_data)
        
        # Store in new tier
        new_storage_path = await target_provider.store(object_id, compressed_data, metadata)
        
        # Delete from old tier (handle deduplication)
        old_storage_path = await self._get_storage_path(object_id)
        if old_storage_path:
            old_provider = self.tier_providers[metadata.tier]
            should_delete = True
            
            if policy.deduplication:
                # Check if other objects reference this data
                should_delete = await self.dedup_manager.remove_reference(metadata.checksum)
                if not should_delete:
                    # Add reference for new location
                    await self.dedup_manager.add_reference(metadata.checksum, object_id, new_storage_path)
            
            if should_delete:
                await old_provider.delete(object_id, old_storage_path)
        
        # Update metadata in database
        await self._update_metadata_tier(object_id, target_tier, new_storage_path)
        
        logger.info(f"Migrated object {object_id} from {metadata.tier.value} to {target_tier.value}")
        return True
    
    async def optimize_storage(self) -> Dict[str, Any]:
        """Optimize storage by running maintenance tasks"""
        
        results = {
            "tier_migrations": 0,
            "cleanup_count": 0,
            "compression_savings": 0,
            "deduplication_savings": 0
        }
        
        # Run tier optimization
        migration_count = await self._optimize_tiers()
        results["tier_migrations"] = migration_count
        
        # Run cleanup
        cleanup_count = await self._cleanup_expired_objects()
        results["cleanup_count"] = cleanup_count
        
        # Calculate savings
        stats = await self.get_storage_stats()
        results["compression_savings"] = stats.compression_ratio
        results["deduplication_savings"] = stats.deduplication_ratio
        
        logger.info(f"Storage optimization completed: {results}")
        return results
    
    async def get_storage_stats(self) -> StorageStats:
        """Get comprehensive storage statistics"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            # Total objects and sizes
            cursor = conn.execute("""
                SELECT 
                    COUNT(*),
                    SUM(original_size),
                    SUM(compressed_size),
                    tier
                FROM object_metadata 
                GROUP BY tier
            """)
            
            tier_stats = {}
            total_objects = 0
            total_original_size = 0
            total_compressed_size = 0
            
            for row in cursor.fetchall():
                count, orig_size, comp_size, tier = row
                tier_stats[StorageTier(tier)] = count
                total_objects += count
                total_original_size += orig_size or 0
                total_compressed_size += comp_size or 0
            
            # Access patterns
            cursor = conn.execute("""
                SELECT 
                    CASE 
                        WHEN access_count >= 10 THEN 'frequent'
                        WHEN access_count >= 3 THEN 'regular'
                        WHEN access_count >= 1 THEN 'occasional'
                        ELSE 'rare'
                    END as pattern,
                    COUNT(*)
                FROM object_metadata
                GROUP BY pattern
            """)
            
            access_patterns = {}
            for row in cursor.fetchall():
                pattern, count = row
                access_patterns[AccessPattern(pattern)] = count
        
        # Get deduplication stats
        dedup_stats = await self.dedup_manager.get_stats()
        
        # Calculate ratios
        compression_ratio = (total_original_size - total_compressed_size) / total_original_size if total_original_size > 0 else 0
        deduplication_ratio = dedup_stats.get("deduplication_ratio", 0)
        storage_efficiency = compression_ratio + deduplication_ratio - (compression_ratio * deduplication_ratio)
        
        return StorageStats(
            total_objects=total_objects,
            total_size_bytes=total_original_size,
            compressed_size_bytes=total_compressed_size,
            compression_ratio=compression_ratio,
            deduplication_ratio=deduplication_ratio,
            tier_distribution=tier_stats,
            access_patterns=access_patterns,
            storage_efficiency=storage_efficiency
        )
    
    def _determine_initial_tier(self, data_size: int, policy: StoragePolicy) -> StorageTier:
        """Determine initial storage tier based on data size and policy"""
        
        # Check size limits for each tier
        for tier in [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD]:
            tier_rules = policy.tier_rules.get(tier, {})
            max_size_mb = tier_rules.get("max_size_mb")
            
            if max_size_mb and data_size <= max_size_mb * 1024 * 1024:
                return tier
        
        # Default to archive tier
        return StorageTier.ARCHIVE
    
    async def _get_metadata(self, object_id: str) -> Optional[StorageMetadata]:
        """Get metadata for an object from database"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    object_id, original_size, compressed_size, compression_type,
                    checksum, tier, created_at, last_accessed, access_count,
                    is_deduplicated, dedup_refs, tags, policy_name
                FROM object_metadata 
                WHERE object_id = ?
            """, (object_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return StorageMetadata(
                object_id=row[0],
                original_size=row[1],
                compressed_size=row[2],
                compression_type=CompressionType(row[3]),
                checksum=row[4],
                tier=StorageTier(row[5]),
                created_at=datetime.fromisoformat(row[6]),
                last_accessed=datetime.fromisoformat(row[7]),
                access_count=row[8],
                is_deduplicated=bool(row[9]),
                dedup_refs=row[10],
                tags=json.loads(row[11]),
                policy_name=row[12]
            )
    
    async def _store_metadata(self, metadata: StorageMetadata, storage_path: str):
        """Store metadata in database"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO object_metadata (
                    object_id, original_size, compressed_size, compression_type,
                    checksum, tier, storage_path, created_at, last_accessed,
                    access_count, is_deduplicated, dedup_refs, tags, policy_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metadata.object_id,
                metadata.original_size,
                metadata.compressed_size,
                metadata.compression_type.value,
                metadata.checksum,
                metadata.tier.value,
                storage_path,
                metadata.created_at.isoformat(),
                metadata.last_accessed.isoformat(),
                metadata.access_count,
                metadata.is_deduplicated,
                metadata.dedup_refs,
                json.dumps(metadata.tags),
                metadata.policy_name
            ))
            conn.commit()
    
    async def _get_storage_path(self, object_id: str) -> Optional[str]:
        """Get storage path for an object"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            cursor = conn.execute(
                "SELECT storage_path FROM object_metadata WHERE object_id = ?",
                (object_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
    
    async def _update_access_stats(self, object_id: str):
        """Update access statistics for an object"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            conn.execute("""
                UPDATE object_metadata 
                SET last_accessed = ?, access_count = access_count + 1
                WHERE object_id = ?
            """, (datetime.utcnow().isoformat(), object_id))
            conn.commit()
    
    async def _delete_metadata(self, object_id: str):
        """Delete metadata for an object"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            conn.execute("DELETE FROM object_metadata WHERE object_id = ?", (object_id,))
            conn.commit()
    
    async def _update_metadata_tier(self, object_id: str, tier: StorageTier, storage_path: str):
        """Update tier and storage path for an object"""
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            conn.execute("""
                UPDATE object_metadata 
                SET tier = ?, storage_path = ?
                WHERE object_id = ?
            """, (tier.value, storage_path, object_id))
            conn.commit()
    
    async def _check_tier_migration(self, object_id: str, metadata: StorageMetadata):
        """Check if an object should be migrated to a different tier"""
        
        policy = self.policies[metadata.policy_name]
        current_tier = metadata.tier
        
        # Calculate age
        age_days = (datetime.utcnow() - metadata.created_at).days
        
        # Determine optimal tier based on access pattern and age
        optimal_tier = current_tier
        
        for tier in [StorageTier.HOT, StorageTier.WARM, StorageTier.COLD, StorageTier.ARCHIVE]:
            tier_rules = policy.tier_rules.get(tier, {})
            
            max_age = tier_rules.get("max_age_days")
            access_threshold = tier_rules.get("access_threshold", 0)
            
            # Check if object fits in this tier
            if (max_age is None or age_days <= max_age) and metadata.access_count >= access_threshold:
                optimal_tier = tier
                break
        
        # Migrate if needed
        if optimal_tier != current_tier:
            await self.migrate_object(object_id, optimal_tier)
    
    async def _optimize_tiers(self) -> int:
        """Optimize storage tiers for all objects"""
        
        migration_count = 0
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            cursor = conn.execute("SELECT object_id FROM object_metadata")
            object_ids = [row[0] for row in cursor.fetchall()]
        
        for object_id in object_ids:
            metadata = await self._get_metadata(object_id)
            if metadata:
                old_tier = metadata.tier
                await self._check_tier_migration(object_id, metadata)
                
                # Check if tier changed
                new_metadata = await self._get_metadata(object_id)
                if new_metadata and new_metadata.tier != old_tier:
                    migration_count += 1
        
        return migration_count
    
    async def _cleanup_expired_objects(self) -> int:
        """Clean up expired objects based on retention policies"""
        
        cleanup_count = 0
        
        with sqlite3.connect(self.metadata_db_path) as conn:
            cursor = conn.execute("""
                SELECT object_id, policy_name, created_at 
                FROM object_metadata
            """)
            
            for row in cursor.fetchall():
                object_id, policy_name, created_at_str = row
                policy = self.policies.get(policy_name, self.default_policy)
                
                if policy.retention_days:
                    created_at = datetime.fromisoformat(created_at_str)
                    age_days = (datetime.utcnow() - created_at).days
                    
                    if age_days > policy.retention_days:
                        await self.delete_object(object_id)
                        cleanup_count += 1
        
        return cleanup_count


class HierarchicalPartyBox(IPartyBox):
    """Enhanced Party Box with hierarchical storage management"""
    
    def __init__(self, base_path: str = "./hierarchical_party_box", policy=None):
        self.base_path = Path(base_path)
        self.policy = policy
        self.hsm = HierarchicalStorageManager(str(self.base_path / "hsm"))
        
        # Category mappings
        self.category_tags = {
            "incoming": {"category": "incoming", "direction": "inbound"},
            "outgoing": {"category": "outgoing", "direction": "outbound"},
            "quarantine": {"category": "quarantine", "status": "quarantined"},
            "attachments": {"category": "attachments", "type": "attachment"}
        }
        
        logger.info(f"Hierarchical Party Box initialized at: {self.base_path}")
    
    async def store_attachment(self, attachment_id: str, content: bytes) -> str:
        """Store an attachment using hierarchical storage (interface method)"""
        
        tags = self.category_tags["attachments"].copy()
        tags["attachment_id"] = attachment_id
        
        metadata = await self.hsm.store_object(
            object_id=attachment_id,
            data=content,
            tags=tags
        )
        
        logger.debug(f"Stored attachment {attachment_id} in {metadata.tier.value} tier")
        return attachment_id
    
    async def store_attachment_with_torch(self, torch_id: str, filename: str, content: bytes) -> str:
        """Store an attachment with torch_id and filename (for test compatibility)"""
        
        # Create a unique attachment ID combining torch_id and filename
        attachment_id = f"{torch_id}_{filename}"
        
        tags = self.category_tags["attachments"].copy()
        tags["attachment_id"] = attachment_id
        tags["torch_id"] = torch_id
        tags["filename"] = filename
        
        metadata = await self.hsm.store_object(
            object_id=attachment_id,
            data=content,
            tags=tags
        )
        
        logger.debug(f"Stored attachment {attachment_id} in {metadata.tier.value} tier")
        return attachment_id
    
    async def retrieve_attachment(self, attachment_id: str) -> Optional[bytes]:
        """Retrieve an attachment from hierarchical storage"""
        
        content = await self.hsm.retrieve_object(attachment_id)
        if content:
            logger.debug(f"Retrieved attachment {attachment_id}")
        else:
            logger.warning(f"Attachment {attachment_id} not found")
        
        return content
    
    async def get_attachment(self, torch_id: str, attachment_id: str) -> Optional[bytes]:
        """Get an attachment by torch_id and attachment_id (for test compatibility)"""
        
        # If attachment_id already includes torch_id, use it directly
        if attachment_id.startswith(f"{torch_id}_"):
            return await self.retrieve_attachment(attachment_id)
        else:
            # Otherwise, construct the full attachment ID
            full_attachment_id = f"{torch_id}_{attachment_id}"
            return await self.retrieve_attachment(full_attachment_id)
    
    async def delete_attachment(self, torch_id_or_attachment_id: str, attachment_id: str = None) -> bool:
        """Delete an attachment from hierarchical storage"""
        
        # Handle both single parameter (attachment_id) and dual parameter (torch_id, attachment_id) calls
        if attachment_id is None:
            # Single parameter call - torch_id_or_attachment_id is actually the attachment_id
            target_attachment_id = torch_id_or_attachment_id
        else:
            # Dual parameter call - construct full attachment_id from torch_id and attachment_id
            if attachment_id.startswith(f"{torch_id_or_attachment_id}_"):
                target_attachment_id = attachment_id
            else:
                target_attachment_id = f"{torch_id_or_attachment_id}_{attachment_id}"
        
        result = await self.hsm.delete_object(target_attachment_id)
        if result:
            logger.debug(f"Deleted attachment {target_attachment_id}")
        else:
            logger.warning(f"Failed to delete attachment {target_attachment_id}")
        
        return result
    
    async def list_attachments(self, torch_id_or_category: str = "all") -> List[Dict[str, Any]]:
        """List attachments for a torch_id or category"""
        
        if torch_id_or_category == "all":
            object_ids = await self.hsm.list_objects()
        elif torch_id_or_category in self.category_tags:
            # It's a category
            tags = self.category_tags[torch_id_or_category]
            object_ids = await self.hsm.list_objects(tags=tags)
        else:
            # It's a torch_id, search for attachments with this torch_id
            tags = {"torch_id": torch_id_or_category}
            object_ids = await self.hsm.list_objects(tags=tags)
        
        # Convert object IDs to attachment info dictionaries
        attachments = []
        for object_id in object_ids:
            metadata = await self.hsm.get_object_metadata(object_id)
            if metadata and metadata.tags:
                attachment_info = {
                    "attachment_id": object_id,
                    "filename": metadata.tags.get("filename", object_id),
                    "size": metadata.original_size,
                    "created_at": metadata.created_at.isoformat() if metadata.created_at else None,
                    "tier": metadata.tier.value if metadata.tier else "unknown"
                }
                attachments.append(attachment_info)
        
        return attachments
    
    async def move_to_quarantine(self, attachment_id: str) -> bool:
        """Move an attachment to quarantine"""
        
        # Get current metadata
        metadata = await self.hsm.get_object_metadata(attachment_id)
        if not metadata:
            return False
        
        # Update tags to mark as quarantined
        quarantine_tags = self.category_tags["quarantine"].copy()
        quarantine_tags.update(metadata.tags)
        quarantine_tags["quarantined_at"] = datetime.utcnow().isoformat()
        quarantine_tags["original_category"] = metadata.tags.get("category", "unknown")
        
        # Retrieve and re-store with new tags
        content = await self.hsm.retrieve_object(attachment_id)
        if content:
            await self.hsm.delete_object(attachment_id)
            await self.hsm.store_object(
                object_id=attachment_id,
                data=content,
                tags=quarantine_tags,
                tier=StorageTier.COLD  # Quarantined items go to cold storage
            )
            
            logger.info(f"Moved attachment {attachment_id} to quarantine")
            return True
        
        return False
    
    async def cleanup_old_attachments(self, max_age_days: int = 30) -> int:
        """Clean up old attachments using HSM optimization"""
        
        # Update retention policy
        policy = self.hsm.policies["default"]
        policy.retention_days = max_age_days
        
        # Run optimization
        results = await self.hsm.optimize_storage()
        cleanup_count = results.get("cleanup_count", 0)
        
        logger.info(f"Cleaned up {cleanup_count} old attachments")
        return cleanup_count
    
    async def get_storage_stats(self) -> Dict[str, Any]:
        """Get comprehensive storage statistics"""
        
        hsm_stats = await self.hsm.get_storage_stats()
        
        return {
            "base_path": str(self.base_path),
            "total_objects": hsm_stats.total_objects,
            "total_size_bytes": hsm_stats.total_size_bytes,
            "total_size_mb": round(hsm_stats.total_size_bytes / (1024 * 1024), 2),
            "compressed_size_bytes": hsm_stats.compressed_size_bytes,
            "compressed_size_mb": round(hsm_stats.compressed_size_bytes / (1024 * 1024), 2),
            "compression_ratio": hsm_stats.compression_ratio,
            "deduplication_ratio": hsm_stats.deduplication_ratio,
            "storage_efficiency": hsm_stats.storage_efficiency,
            "tier_distribution": {tier.value: count for tier, count in hsm_stats.tier_distribution.items()},
            "access_patterns": {pattern.value: count for pattern, count in hsm_stats.access_patterns.items()}
        }
    
    async def optimize_storage(self) -> Dict[str, Any]:
        """Optimize storage using HSM"""
        return await self.hsm.optimize_storage()
    
    async def migrate_attachment(self, attachment_id: str, target_tier: str) -> bool:
        """Migrate an attachment to a specific storage tier"""
        try:
            tier = StorageTier(target_tier)
            return await self.hsm.migrate_object(attachment_id, tier)
        except ValueError:
            logger.error(f"Invalid storage tier: {target_tier}")
            return False
    
    def __repr__(self) -> str:
        return f"HierarchicalPartyBox(base_path='{self.base_path}')"


# Convenience functions
async def create_hierarchical_party_box(base_path: str = "./hierarchical_party_box") -> HierarchicalPartyBox:
    """Create and initialize a hierarchical Party Box"""
    return HierarchicalPartyBox(base_path)


async def migrate_from_filesystem_party_box(
    old_party_box: "FileSystemPartyBox",
    new_party_box: HierarchicalPartyBox
) -> Dict[str, Any]:
    """Migrate data from FileSystemPartyBox to HierarchicalPartyBox"""
    
    migration_stats = {
        "migrated_count": 0,
        "failed_count": 0,
        "total_size_bytes": 0
    }
    
    # Get all attachments from old party box
    all_attachments = await old_party_box.list_attachments()
    
    for attachment_id in all_attachments:
        try:
            # Retrieve from old party box
            content = await old_party_box.retrieve_attachment(attachment_id)
            if content:
                # Store in new party box
                await new_party_box.store_attachment(attachment_id, content)
                migration_stats["migrated_count"] += 1
                migration_stats["total_size_bytes"] += len(content)
            else:
                migration_stats["failed_count"] += 1
                
        except Exception as e:
            logger.error(f"Failed to migrate attachment {attachment_id}: {e}")
            migration_stats["failed_count"] += 1
    
    logger.info(f"Migration completed: {migration_stats}")
    return migration_stats