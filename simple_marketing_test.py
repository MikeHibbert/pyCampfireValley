#!/usr/bin/env python3
"""
Simple Marketing Team Test
==========================

A simplified test script that sends a website development request
directly to the dockerized development team without complex MCP setup.
"""

import asyncio
import aiohttp
import json
from datetime import datetime


async def test_development_team():
    """Send a simple test request to the development team."""
    
    # Create a properly formatted request
    test_request = {
        "idea_id": "test_001",
        "category": "E-commerce Innovation",
        "strategic_requirements": "Create an innovative e-commerce platform that addresses current market gaps and provides unique value to both buyers and sellers. Focus on sustainability and local businesses.",
        "creative_requirements": "Modern, clean design with emphasis on sustainability. Use green color palette and eco-friendly imagery. Mobile-first responsive design.",
        "ux_requirements": "Intuitive navigation, fast checkout process, personalized recommendations, and accessibility compliance. Focus on user trust and security.",
        "timestamp": datetime.now().isoformat(),
        "source_team": "marketing_team"
    }
    
    print("🔥 Testing CampfireValley Development Team")
    print("=" * 50)
    print(f"📤 Sending request: {test_request['idea_id']}")
    print(f"📋 Category: {test_request['category']}")
    
    try:
        # Check health first
        async with aiohttp.ClientSession() as session:
            print("\n🏥 Checking development team health...")
            async with session.get("http://localhost:8080/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print(f"✅ Health check passed: {health_data['status']}")
                else:
                    print(f"❌ Health check failed: {response.status}")
                    return
            
            print("\n📤 Sending development request...")
            async with session.post(
                "http://localhost:8080/api/develop_website",
                json=test_request,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                print(f"📊 Response status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print("✅ Request successful!")
                    print(f"📋 Response: {json.dumps(result, indent=2)}")
                else:
                    error_text = await response.text()
                    print(f"❌ Request failed: {error_text}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "=" * 50)
    print("🔥 Test completed!")


if __name__ == "__main__":
    asyncio.run(test_development_team())