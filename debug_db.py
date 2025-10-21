#!/usr/bin/env python3

import tempfile
import asyncio
from pathlib import Path
from campfirevalley.hierarchical_storage import HierarchicalPartyBox, StoragePolicy, StorageTier
from campfirevalley.models import Torch

async def test_debug():
    """Debug the database issue"""
    print("Starting debug test...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Temp dir: {temp_dir}")
        
        policy = StoragePolicy(
            name="test",
            tier_rules={
                StorageTier.HOT: {"retention_days": 1},
                StorageTier.WARM: {"retention_days": 7},
                StorageTier.COLD: {"retention_days": 30},
                StorageTier.ARCHIVE: {"retention_days": 365}
            }
        )
        
        print("Creating HierarchicalPartyBox...")
        party_box = HierarchicalPartyBox(temp_dir)
        print("HierarchicalPartyBox created successfully")
        
        # Create test torch
        torch = Torch(
            claim="integration test",
            source_campfire="test_campfire",
            channel="test_channel",
            torch_id="test_torch_001",
            sender_valley="test_valley",
            target_address="test_valley:test_campfire",
            signature="test_signature",
            data={"test": "data"}
        )
        
        print("Creating test data...")
        test_data = b"test image data" * 50
        
        print("Storing attachment...")
        try:
            attachment_id = await party_box.store_attachment_with_torch(
                torch.torch_id, "test_image.jpg", test_data
            )
            print(f"Attachment stored successfully: {attachment_id}")
        except Exception as e:
            print(f"Error storing attachment: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_debug())