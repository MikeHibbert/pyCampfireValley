"""
Tests for the hierarchical storage system.
"""

import pytest
import asyncio
import tempfile
import shutil
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from campfirevalley.hierarchical_storage import (
    HierarchicalStorageManager, StorageTier, StoragePolicy, CompressionType,
    AccessPattern, DataLifecycleManager, StorageOptimizer, DeduplicationEngine,
    CompressionEngine, HierarchicalPartyBox
)
from campfirevalley.party_box import PartyBoxManager, create_hierarchical_party_box
from campfirevalley.models import Torch


class TestStorageTier:
    """Test StorageTier enum."""
    
    def test_storage_tier_values(self):
        """Test that StorageTier has expected values."""
        assert StorageTier.HOT.value == "hot"
        assert StorageTier.WARM.value == "warm"
        assert StorageTier.COLD.value == "cold"
        assert StorageTier.ARCHIVE.value == "archive"


class TestStoragePolicy:
    """Test StoragePolicy dataclass."""
    
    def test_storage_policy_creation(self):
        """Test creating a storage policy."""
        policy = StoragePolicy(
            name="test_policy",
            hot_retention_days=7,
            warm_retention_days=30,
            cold_retention_days=365,
            archive_retention_days=2555,
            compression_threshold_mb=100,
            deduplication_enabled=True,
            auto_tier_enabled=True
        )
        
        assert policy.name == "test_policy"
        assert policy.hot_retention_days == 7
        assert policy.warm_retention_days == 30
        assert policy.cold_retention_days == 365
        assert policy.archive_retention_days == 2555
        assert policy.compression_threshold_mb == 100
        assert policy.deduplication_enabled is True
        assert policy.auto_tier_enabled is True


class TestCompressionEngine:
    """Test CompressionEngine."""
    
    def test_compression_engine_creation(self):
        """Test creating a compression engine."""
        engine = CompressionEngine()
        assert engine.compression_type == CompressionType.GZIP
        assert engine.compression_level == 6
    
    def test_compress_data(self):
        """Test data compression."""
        engine = CompressionEngine()
        data = b"Hello, World!" * 100  # Repeating data compresses well
        
        compressed = engine.compress(data)
        assert len(compressed) < len(data)
        assert compressed != data
    
    def test_decompress_data(self):
        """Test data decompression."""
        engine = CompressionEngine()
        original_data = b"Hello, World!" * 100
        
        compressed = engine.compress(original_data)
        decompressed = engine.decompress(compressed)
        
        assert decompressed == original_data
    
    def test_compression_ratio(self):
        """Test compression ratio calculation."""
        engine = CompressionEngine()
        data = b"A" * 1000  # Highly compressible data
        
        compressed = engine.compress(data)
        ratio = engine.get_compression_ratio(data, compressed)
        
        assert ratio > 1.0  # Should achieve good compression


class TestDeduplicationEngine:
    """Test DeduplicationEngine."""
    
    def test_deduplication_engine_creation(self):
        """Test creating a deduplication engine."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = DeduplicationEngine(temp_dir)
            assert engine.storage_path == temp_dir
    
    def test_calculate_hash(self):
        """Test hash calculation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = DeduplicationEngine(temp_dir)
            data = b"test data"
            
            hash1 = engine._calculate_hash(data)
            hash2 = engine._calculate_hash(data)
            
            assert hash1 == hash2
            assert len(hash1) == 64  # SHA-256 hex digest
    
    def test_store_and_retrieve_data(self):
        """Test storing and retrieving deduplicated data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = DeduplicationEngine(temp_dir)
            data = b"test data for deduplication"
            
            # Store data
            hash_value = engine.store_data(data)
            assert hash_value is not None
            
            # Retrieve data
            retrieved = engine.get_data(hash_value)
            assert retrieved == data
    
    def test_deduplication(self):
        """Test that duplicate data is deduplicated."""
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = DeduplicationEngine(temp_dir)
            data = b"duplicate data"
            
            # Store same data twice
            hash1 = engine.store_data(data)
            hash2 = engine.store_data(data)
            
            # Should get same hash
            assert hash1 == hash2
            
            # Should only have one file
            chunk_files = list(Path(temp_dir).glob("chunks/*"))
            assert len(chunk_files) == 1


class TestDataLifecycleManager:
    """Test DataLifecycleManager."""
    
    def test_lifecycle_manager_creation(self):
        """Test creating a lifecycle manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            manager = DataLifecycleManager(temp_dir, policy)
            assert manager.storage_path == temp_dir
            assert manager.policy == policy
    
    def test_determine_tier_new_file(self):
        """Test tier determination for new files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            manager = DataLifecycleManager(temp_dir, policy)
            
            # New file should be HOT
            tier = manager.determine_tier("new_file.txt", AccessPattern.FREQUENT)
            assert tier == StorageTier.HOT
    
    @patch('os.path.getmtime')
    def test_determine_tier_old_file(self, mock_getmtime):
        """Test tier determination for old files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            manager = DataLifecycleManager(temp_dir, policy)
            
            # Mock file that's 10 days old
            old_time = (datetime.now() - timedelta(days=10)).timestamp()
            mock_getmtime.return_value = old_time
            
            tier = manager.determine_tier("old_file.txt", AccessPattern.INFREQUENT)
            assert tier == StorageTier.WARM


class TestStorageOptimizer:
    """Test StorageOptimizer."""
    
    def test_optimizer_creation(self):
        """Test creating a storage optimizer."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            optimizer = StorageOptimizer(temp_dir, policy)
            assert optimizer.storage_path == temp_dir
            assert optimizer.policy == policy
    
    @pytest.mark.asyncio
    async def test_optimize_storage(self):
        """Test storage optimization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365,
                compression_threshold_mb=0,  # Compress everything
                deduplication_enabled=True
            )
            optimizer = StorageOptimizer(temp_dir, policy)
            
            # Create test file
            test_file = Path(temp_dir) / "test.txt"
            test_file.write_text("test data")
            
            stats = await optimizer.optimize_storage()
            assert "files_processed" in stats
            assert "space_saved" in stats


class TestHierarchicalStorageManager:
    """Test HierarchicalStorageManager."""
    
    def test_hsm_creation(self):
        """Test creating hierarchical storage manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            hsm = HierarchicalStorageManager(temp_dir, policy)
            assert hsm.storage_path == temp_dir
            assert hsm.policy == policy
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_data(self):
        """Test storing and retrieving data through HSM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            hsm = HierarchicalStorageManager(temp_dir, policy)
            
            data = b"test data for HSM"
            file_id = "test_file.txt"
            
            # Store data
            await hsm.store_data(file_id, data, AccessPattern.FREQUENT)
            
            # Retrieve data
            retrieved = await hsm.retrieve_data(file_id)
            assert retrieved == data
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self):
        """Test getting storage statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            hsm = HierarchicalStorageManager(temp_dir, policy)
            
            # Store some data
            await hsm.store_data("file1.txt", b"data1", AccessPattern.FREQUENT)
            await hsm.store_data("file2.txt", b"data2", AccessPattern.INFREQUENT)
            
            stats = await hsm.get_storage_stats()
            assert "total_files" in stats
            assert "total_size" in stats
            assert "tier_distribution" in stats


class TestHierarchicalPartyBox:
    """Test HierarchicalPartyBox."""
    
    def test_hierarchical_party_box_creation(self):
        """Test creating hierarchical party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            party_box = HierarchicalPartyBox(temp_dir, policy)
            assert party_box.base_path == temp_dir
            assert party_box.policy == policy
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_attachment(self):
        """Test storing and retrieving attachments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            party_box = HierarchicalPartyBox(temp_dir, policy)
            
            # Create test torch
            torch = Torch(
                id="test_torch",
                content={"message": "test"},
                sender="test_sender",
                recipient="test_recipient"
            )
            
            attachment_data = b"test attachment data"
            
            # Store attachment
            attachment_id = await party_box.store_attachment(
                torch.id, "test.txt", attachment_data
            )
            assert attachment_id is not None
            
            # Retrieve attachment
            retrieved = await party_box.get_attachment(torch.id, attachment_id)
            assert retrieved == attachment_data
    
    @pytest.mark.asyncio
    async def test_list_attachments(self):
        """Test listing attachments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            party_box = HierarchicalPartyBox(temp_dir, policy)
            
            torch_id = "test_torch"
            
            # Store multiple attachments
            await party_box.store_attachment(torch_id, "file1.txt", b"data1")
            await party_box.store_attachment(torch_id, "file2.txt", b"data2")
            
            # List attachments
            attachments = await party_box.list_attachments(torch_id)
            assert len(attachments) == 2
            assert any(att["filename"] == "file1.txt" for att in attachments)
            assert any(att["filename"] == "file2.txt" for att in attachments)
    
    @pytest.mark.asyncio
    async def test_delete_attachment(self):
        """Test deleting attachments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            party_box = HierarchicalPartyBox(temp_dir, policy)
            
            torch_id = "test_torch"
            
            # Store attachment
            attachment_id = await party_box.store_attachment(
                torch_id, "test.txt", b"test data"
            )
            
            # Verify it exists
            attachments = await party_box.list_attachments(torch_id)
            assert len(attachments) == 1
            
            # Delete attachment
            await party_box.delete_attachment(torch_id, attachment_id)
            
            # Verify it's gone
            attachments = await party_box.list_attachments(torch_id)
            assert len(attachments) == 0
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self):
        """Test getting storage statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            party_box = HierarchicalPartyBox(temp_dir, policy)
            
            # Store some attachments
            await party_box.store_attachment("torch1", "file1.txt", b"data1")
            await party_box.store_attachment("torch2", "file2.txt", b"data2")
            
            stats = await party_box.get_storage_stats()
            assert "total_attachments" in stats
            assert "total_size" in stats
            assert "tier_distribution" in stats


class TestPartyBoxManager:
    """Test PartyBoxManager."""
    
    def test_party_box_manager_creation(self):
        """Test creating party box manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager(temp_dir)
            assert manager.base_path == temp_dir
    
    def test_create_filesystem_party_box(self):
        """Test creating filesystem party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager(temp_dir)
            
            party_box = manager.create_party_box("test_box", "filesystem")
            assert party_box is not None
            assert hasattr(party_box, 'base_path')
    
    def test_create_hierarchical_party_box(self):
        """Test creating hierarchical party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager(temp_dir)
            
            policy = StoragePolicy(
                name="test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365
            )
            
            party_box = manager.create_party_box(
                "test_box", "hierarchical", policy=policy
            )
            assert party_box is not None
            assert hasattr(party_box, 'policy')
    
    def test_get_party_box(self):
        """Test getting existing party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager(temp_dir)
            
            # Create party box
            original = manager.create_party_box("test_box", "filesystem")
            
            # Get party box
            retrieved = manager.get_party_box("test_box")
            assert retrieved is not None
    
    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting manager statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager(temp_dir)
            
            # Create some party boxes
            manager.create_party_box("box1", "filesystem")
            manager.create_party_box("box2", "filesystem")
            
            stats = await manager.get_statistics()
            assert "total_party_boxes" in stats
            assert stats["total_party_boxes"] == 2


class TestIntegration:
    """Integration tests for hierarchical storage system."""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete hierarchical storage workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create hierarchical party box
            policy = StoragePolicy(
                name="integration_test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365,
                compression_threshold_mb=0,  # Compress everything
                deduplication_enabled=True,
                auto_tier_enabled=True
            )
            
            party_box = create_hierarchical_party_box(temp_dir, policy)
            
            # Create test torch
            torch = Torch(
                id="integration_torch",
                content={"message": "integration test"},
                sender="test_sender",
                recipient="test_recipient"
            )
            
            # Store multiple attachments
            attachment1_id = await party_box.store_attachment(
                torch.id, "document.txt", b"Important document content" * 100
            )
            attachment2_id = await party_box.store_attachment(
                torch.id, "image.jpg", b"Binary image data" * 50
            )
            
            # Verify attachments exist
            attachments = await party_box.list_attachments(torch.id)
            assert len(attachments) == 2
            
            # Retrieve attachments
            doc_data = await party_box.get_attachment(torch.id, attachment1_id)
            img_data = await party_box.get_attachment(torch.id, attachment2_id)
            
            assert doc_data == b"Important document content" * 100
            assert img_data == b"Binary image data" * 50
            
            # Get storage statistics
            stats = await party_box.get_storage_stats()
            assert stats["total_attachments"] == 2
            assert stats["total_size"] > 0
            
            # Optimize storage
            optimization_stats = await party_box.optimize_storage()
            assert "files_processed" in optimization_stats
    
    @pytest.mark.asyncio
    async def test_deduplication_workflow(self):
        """Test deduplication in hierarchical storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="dedup_test",
                hot_retention_days=1,
                warm_retention_days=7,
                cold_retention_days=30,
                archive_retention_days=365,
                deduplication_enabled=True
            )
            
            party_box = create_hierarchical_party_box(temp_dir, policy)
            
            # Store same data multiple times
            duplicate_data = b"This is duplicate data" * 100
            
            torch1_id = "torch1"
            torch2_id = "torch2"
            
            # Store same data in different torches
            await party_box.store_attachment(torch1_id, "file1.txt", duplicate_data)
            await party_box.store_attachment(torch2_id, "file2.txt", duplicate_data)
            
            # Both should be retrievable
            data1 = await party_box.get_attachment(torch1_id, "file1.txt")
            data2 = await party_box.get_attachment(torch2_id, "file2.txt")
            
            assert data1 == duplicate_data
            assert data2 == duplicate_data
            
            # Storage should be optimized due to deduplication
            stats = await party_box.get_storage_stats()
            assert stats["total_attachments"] == 2


if __name__ == "__main__":
    pytest.main([__file__])