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
    AccessPattern, CompressionManager, DeduplicationManager, HierarchicalPartyBox
)
from campfirevalley.party_box import PartyBoxManager
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
            tier_rules={
                StorageTier.HOT: {"max_size_gb": 10, "retention_days": 7},
                StorageTier.WARM: {"max_size_gb": 100, "retention_days": 30},
                StorageTier.COLD: {"max_size_gb": 1000, "retention_days": 365},
                StorageTier.ARCHIVE: {"retention_days": 2555}
            },
            compression=CompressionType.LZ4,
            deduplication=True,
            auto_tier=True
        )
        
        assert policy.name == "test_policy"
        assert policy.tier_rules[StorageTier.HOT]["retention_days"] == 7
        assert policy.tier_rules[StorageTier.WARM]["retention_days"] == 30
        assert policy.compression == CompressionType.LZ4
        assert policy.deduplication == True
        assert policy.auto_tier == True
        assert policy.tier_rules[StorageTier.COLD]["retention_days"] == 365
        assert policy.tier_rules[StorageTier.ARCHIVE]["retention_days"] == 2555


class TestCompressionManager:
    """Test CompressionManager."""
    
    @pytest.mark.asyncio
    async def test_compression_manager_compress(self):
        """Test data compression."""
        data = b"Hello, World!" * 100  # Repeating data compresses well
        
        compressed = await CompressionManager.compress(data, CompressionType.LZ4)
        assert len(compressed) < len(data)
        assert compressed != data
    
    @pytest.mark.asyncio
    async def test_compression_manager_decompress(self):
        """Test data decompression."""
        original_data = b"Hello, World!" * 100
        
        compressed = await CompressionManager.compress(original_data, CompressionType.LZ4)
        decompressed = await CompressionManager.decompress(compressed, CompressionType.LZ4)
        
        assert decompressed == original_data
    
    @pytest.mark.asyncio
    async def test_compression_none(self):
        """Test no compression."""
        data = b"test data"
        
        compressed = await CompressionManager.compress(data, CompressionType.NONE)
        assert compressed == data
        
        decompressed = await CompressionManager.decompress(compressed, CompressionType.NONE)
        assert decompressed == data


class TestDeduplicationManager:
    """Test DeduplicationManager."""
    
    def test_deduplication_manager_creation(self):
        """Test creating a deduplication manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "dedup.db")
            manager = DeduplicationManager(db_path)
            assert manager.db_path == db_path
    
    @pytest.mark.asyncio
    async def test_check_duplicate(self):
        """Test checking for duplicates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "dedup.db")
            manager = DeduplicationManager(db_path)
            
            # Should return None for non-existent checksum
            result = await manager.check_duplicate("nonexistent_checksum")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_add_reference(self):
        """Test adding deduplication reference."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "dedup.db")
            manager = DeduplicationManager(db_path)
            
            # Add a reference
            await manager.add_reference("test_checksum", "test_object", "/test/path")
            
            # Check if it exists
            result = await manager.check_duplicate("test_checksum")
            assert result is not None
            assert result[0] == "test_object"





class TestHierarchicalStorageManager:
    """Test HierarchicalStorageManager."""
    
    def test_hsm_creation(self):
        """Test creating hierarchical storage manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            hsm = HierarchicalStorageManager(temp_dir)
            assert hsm.base_path == Path(temp_dir)
            assert "default" in hsm.policies
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_object(self):
        """Test storing and retrieving objects through HSM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            hsm = HierarchicalStorageManager(temp_dir)
            
            test_data = b"test data for storage"
            
            # Store object
            object_id = "test_object_001"
            metadata = await hsm.store_object(
                object_id,
                test_data,
                tags={"content_type": "text/plain", "source": "test"}
            )
            assert object_id is not None
            
            # Retrieve object
            retrieved_data = await hsm.retrieve_object(object_id)
            assert retrieved_data == test_data
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_data(self):
        """Test storing and retrieving data through HSM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            hsm = HierarchicalStorageManager(temp_dir)
            
            data = b"test data for HSM"
            file_id = "test_file.txt"
            
            # Store data
            await hsm.store_object(file_id, data)
            
            # Retrieve data
            retrieved = await hsm.retrieve_object(file_id)
            assert retrieved == data
    
    @pytest.mark.asyncio
    async def test_get_storage_stats(self):
        """Test getting storage statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            hsm = HierarchicalStorageManager(temp_dir)
            
            # Store some data
            await hsm.store_object("file1.txt", b"data1")
            await hsm.store_object("file2.txt", b"data2")
            
            stats = await hsm.get_storage_stats()
            assert stats.total_objects >= 2
            assert stats.total_size_bytes > 0
            assert stats.tier_distribution is not None


class TestHierarchicalPartyBox:
    """Test HierarchicalPartyBox."""
    
    def test_hierarchical_party_box_creation(self):
        """Test creating hierarchical party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
            assert party_box.base_path == Path(temp_dir)
            assert hasattr(party_box, 'hsm')  # Should have hierarchical storage manager
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_attachment(self):
        """Test storing and retrieving attachments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
             
             # Create test torch
            torch = Torch(
                claim="test claim",
                source_campfire="test_campfire",
                channel="test_channel",
                torch_id="test_torch",
                sender_valley="test_valley",
                target_address="test_valley:test_campfire",
                signature="test_signature",
                data={"message": "test"},
                metadata={"sender": "test_sender", "recipient": "test_recipient"}
            )
            
            attachment_data = b"test attachment data"
            
            # Store attachment
            attachment_id = await party_box.store_attachment_with_torch(
                torch.torch_id, "test.txt", attachment_data
            )
            assert attachment_id is not None
            
            # Retrieve attachment
            retrieved = await party_box.get_attachment(torch.torch_id, attachment_id)
            assert retrieved == attachment_data
    
    @pytest.mark.asyncio
    async def test_list_attachments(self):
        """Test listing attachments."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
            
            torch_id = "test_torch"
            
            # Store multiple attachments
            await party_box.store_attachment_with_torch(torch_id, "file1.txt", b"data1")
            await party_box.store_attachment_with_torch(torch_id, "file2.txt", b"data2")
            
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
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
            
            torch_id = "test_torch"
            
            # Store attachment
            attachment_id = await party_box.store_attachment_with_torch(
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
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
             
             # Store some attachments
            await party_box.store_attachment_with_torch("torch1", "file1.txt", b"data1")
            await party_box.store_attachment_with_torch("torch2", "file2.txt", b"data2")
            
            stats = await party_box.get_storage_stats()
            assert "total_objects" in stats
            assert "total_size_bytes" in stats
            assert "tier_distribution" in stats


class TestPartyBoxManager:
    """Test PartyBoxManager."""
    
    def test_party_box_manager_creation(self):
        """Test creating party box manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager()
            assert hasattr(manager, 'party_boxes')
            assert hasattr(manager, 'default_type')
            assert manager.default_type == "filesystem"
    
    @pytest.mark.asyncio
    async def test_create_filesystem_party_box(self):
        """Test creating filesystem party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager()
            
            party_box = await manager.create_party_box("test_box", "filesystem")
            assert party_box is not None
            assert hasattr(party_box, 'base_path')

    @pytest.mark.asyncio
    async def test_create_hierarchical_party_box(self):
        """Test creating hierarchical party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager()
            
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            
            party_box = await manager.create_party_box(
                "test_box", "hierarchical", policy=policy
            )
            assert party_box is not None
            assert hasattr(party_box, 'policy')

    @pytest.mark.asyncio
    async def test_get_party_box(self):
        """Test getting existing party box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager()
            
            # Create party box
            original = await manager.create_party_box("test_box", "filesystem")
            
            # Get party box
            retrieved = await manager.get_party_box("test_box")
            assert retrieved is not None
    
    @pytest.mark.asyncio
    async def test_get_statistics(self):
        """Test getting manager statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PartyBoxManager()
            
            # Create some party boxes
            await manager.create_party_box("box1", "filesystem")
            await manager.create_party_box("box2", "filesystem")
            
            stats = await manager.get_statistics()
            assert "total_party_boxes" in stats
            assert stats["total_party_boxes"] == 2


class TestIntegration:
    """Integration tests for hierarchical storage system."""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete workflow with HSM and Party Box."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
            
            # Create test torch
            torch = Torch(
                claim="integration test claim",
                source_campfire="test_campfire",
                channel="test_channel",
                torch_id="integration_torch",
                sender_valley="test_valley",
                target_address="test_valley:test_campfire",
                signature="test_signature",
                data={"message": "integration test"},
                metadata={"sender": "test_sender", "recipient": "test_recipient"}
            )
            
            # Store multiple attachments
            attachment1_id = await party_box.store_attachment_with_torch(
                torch.torch_id, "document.txt", b"Important document content" * 100
            )
            attachment2_id = await party_box.store_attachment_with_torch(
                torch.torch_id, "image.jpg", b"Binary image data" * 50
            )
            
            # List attachments
            attachments = await party_box.list_attachments(torch.torch_id)
            assert len(attachments) == 2
            
            # Retrieve attachments
            doc_data = await party_box.get_attachment(torch.torch_id, attachment1_id)
            img_data = await party_box.get_attachment(torch.torch_id, attachment2_id)
            
            assert doc_data == b"Important document content" * 100
            assert img_data == b"Binary image data" * 50
            
            # Get storage statistics
            stats = await party_box.get_storage_stats()
            assert stats["total_objects"] == 2
            assert stats["total_size_bytes"] > 0
    
    @pytest.mark.asyncio
    async def test_deduplication_workflow(self):
        """Test deduplication workflow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            policy = StoragePolicy(
                name="test",
                tier_rules={
                    StorageTier.HOT: {"retention_days": 1},
                    StorageTier.WARM: {"retention_days": 7},
                    StorageTier.COLD: {"retention_days": 30},
                    StorageTier.ARCHIVE: {"retention_days": 365}
                }
            )
            party_box = HierarchicalPartyBox(temp_dir)
             
             # Store duplicate data multiple times
            duplicate_data = b"This is duplicate data" * 100
            
            torch1_id = "torch1"
            torch2_id = "torch2"
            
            # Store same data in different torches
            att1_id = await party_box.store_attachment_with_torch(torch1_id, "file1.txt", duplicate_data)
            att2_id = await party_box.store_attachment_with_torch(torch2_id, "file2.txt", duplicate_data)
            
            # Both should be retrievable
            data1 = await party_box.get_attachment(torch1_id, att1_id)
            data2 = await party_box.get_attachment(torch2_id, att2_id)
            
            assert data1 == duplicate_data
            assert data2 == duplicate_data
            
            # Storage should be optimized due to deduplication
            stats = await party_box.get_storage_stats()
            assert stats["total_objects"] == 2


if __name__ == "__main__":
    pytest.main([__file__])