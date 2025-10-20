#!/usr/bin/env python3
"""
Simplified Marketing Team Demo
==============================

A simplified version of the marketing demo that bypasses MCP subscription issues
and focuses on generating marketing ideas and sending them to the development team.
"""

import asyncio
import json
import logging
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimplifiedMarketingDemo:
    """Simplified marketing demo that bypasses MCP issues."""
    
    def __init__(self, dev_team_url: str = "http://localhost:8080"):
        """Initialize the simplified marketing demo."""
        self.dev_team_url = dev_team_url
        self.demo_results = {
            "marketing_ideas": [],
            "development_requests": [],
            "development_responses": []
        }
        
    async def generate_marketing_ideas(self) -> List[Dict[str, Any]]:
        """Generate marketing ideas without using campfires."""
        logger.info("Generating marketing ideas...")
        
        # Simulate marketing team collaboration with predefined ideas
        marketing_ideas = [
            {
                "id": "idea_1",
                "category": "E-commerce Innovation",
                "timestamp": datetime.now().isoformat(),
                "strategic_analysis": {
                    "content": "Market analysis reveals a gap in sustainable e-commerce platforms. Opportunity exists for a marketplace that prioritizes eco-friendly products and carbon-neutral shipping. Target market: environmentally conscious consumers aged 25-45 with disposable income $50k+. Competitive advantage: integrated carbon offset tracking and sustainability scoring for all products."
                },
                "creative_concept": {
                    "content": "Brand concept: 'EcoMarket' - A clean, green-themed marketplace with earth tones and natural imagery. Key features: sustainability badges, carbon footprint calculator, eco-friendly packaging options. Visual identity emphasizes transparency and trust through clean typography and organic shapes."
                },
                "ux_research": {
                    "content": "User research indicates strong preference for sustainability information at point of purchase. Recommended features: prominent eco-ratings, simplified checkout with carbon offset options, educational content about environmental impact. Mobile-first design essential for target demographic."
                }
            },
            {
                "id": "idea_2", 
                "category": "SaaS Solution",
                "timestamp": datetime.now().isoformat(),
                "strategic_analysis": {
                    "content": "Small businesses struggle with project management and team collaboration. Market opportunity for simplified project management SaaS targeting teams of 5-50 people. Pricing strategy: freemium model with $10/user/month premium tier. Key differentiator: AI-powered task prioritization and deadline prediction."
                },
                "creative_concept": {
                    "content": "Brand concept: 'TeamFlow' - Modern, professional interface with intuitive drag-and-drop functionality. Color scheme: calming blues and energizing oranges. Focus on simplicity and clarity with minimal cognitive load. Dashboard-centric design with customizable widgets."
                },
                "ux_research": {
                    "content": "User testing shows preference for visual project timelines and real-time collaboration features. Critical requirements: mobile app parity, offline functionality, integration with popular tools (Slack, Google Workspace). Onboarding should be completed in under 5 minutes."
                }
            },
            {
                "id": "idea_3",
                "category": "Community Platform", 
                "timestamp": datetime.now().isoformat(),
                "strategic_analysis": {
                    "content": "Growing demand for niche community platforms focused on skill sharing and mentorship. Target market: professionals seeking career development and knowledge exchange. Monetization: premium memberships, sponsored content, and expert consultation fees. Market size: $2B+ professional development sector."
                },
                "creative_concept": {
                    "content": "Brand concept: 'SkillBridge' - Professional yet approachable design emphasizing connection and growth. Visual metaphors of bridges and pathways. Color palette: trustworthy navy blue with accent colors for different skill categories. Profile-centric design showcasing expertise and achievements."
                },
                "ux_research": {
                    "content": "Research indicates users want structured mentorship programs and skill verification systems. Key features: mentor matching algorithm, progress tracking, peer review system. Platform should facilitate both one-on-one and group learning experiences with integrated video calling and resource sharing."
                }
            }
        ]
        
        self.demo_results["marketing_ideas"] = marketing_ideas
        logger.info(f"Generated {len(marketing_ideas)} marketing ideas")
        return marketing_ideas
    
    async def send_ideas_to_development_team(self, ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Send marketing ideas to the development team API."""
        logger.info("Sending ideas to development team...")
        
        development_results = []
        
        for idea in ideas:
            try:
                # Prepare development request matching the expected DevelopmentRequest model
                dev_request = {
                    "idea_id": idea["id"],
                    "category": idea["category"],
                    "strategic_requirements": idea["strategic_analysis"]["content"],
                    "creative_requirements": idea["creative_concept"]["content"], 
                    "ux_requirements": idea["ux_research"]["content"],
                    "timestamp": idea["timestamp"],
                    "source_team": "marketing-team"
                }
                
                logger.info(f"Sending request for {idea['category']}...")
                
                # Send to development team API using the correct endpoint
                response = requests.post(
                    f"{self.dev_team_url}/api/develop_website",
                    json=dev_request,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    dev_response = response.json()
                    development_results.append({
                        "idea_id": idea["id"],
                        "request": dev_request,
                        "response": dev_response,
                        "status": "success"
                    })
                    logger.info(f"Successfully received development analysis for {idea['category']}")
                else:
                    logger.error(f"Development team API error: {response.status_code} - {response.text}")
                    development_results.append({
                        "idea_id": idea["id"],
                        "request": dev_request,
                        "response": None,
                        "status": "error",
                        "error": f"HTTP {response.status_code}: {response.text}"
                    })
                
                # Brief pause between requests
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error sending idea {idea['id']} to development team: {e}")
                development_results.append({
                    "idea_id": idea["id"],
                    "request": dev_request,
                    "response": None,
                    "status": "error",
                    "error": str(e)
                })
        
        self.demo_results["development_requests"] = [r["request"] for r in development_results]
        self.demo_results["development_responses"] = development_results
        
        logger.info(f"Completed {len(development_results)} development requests")
        return development_results
    
    async def generate_report(self) -> str:
        """Generate a simple report of the demo results."""
        report_path = f"simplified_marketing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report_data = {
            "demo_timestamp": datetime.now().isoformat(),
            "summary": {
                "ideas_generated": len(self.demo_results["marketing_ideas"]),
                "development_requests_sent": len(self.demo_results["development_requests"]),
                "successful_responses": len([r for r in self.demo_results["development_responses"] if r["status"] == "success"])
            },
            "results": self.demo_results
        }
        
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        logger.info(f"Report generated: {report_path}")
        return report_path
    
    async def run_demo(self):
        """Run the complete simplified marketing demo."""
        try:
            logger.info("Starting Simplified Marketing Team Demo...")
            
            # Generate marketing ideas
            ideas = await self.generate_marketing_ideas()
            
            # Send ideas to development team
            dev_results = await self.send_ideas_to_development_team(ideas)
            
            # Generate report
            report_path = await self.generate_report()
            
            logger.info("Simplified marketing demo completed successfully!")
            logger.info(f"Report available at: {report_path}")
            
            return {
                "status": "success",
                "ideas_generated": len(ideas),
                "development_requests": len(dev_results),
                "successful_responses": len([r for r in dev_results if r["status"] == "success"]),
                "report_path": report_path
            }
            
        except Exception as e:
            logger.error(f"Demo failed: {e}")
            raise

async def main():
    """Main entry point for the simplified marketing demo."""
    demo = SimplifiedMarketingDemo()
    result = await demo.run_demo()
    
    print("\n" + "="*60)
    print("🔥 SIMPLIFIED MARKETING TEAM DEMO COMPLETE")
    print("="*60)
    print(f"✅ Ideas Generated: {result['ideas_generated']}")
    print(f"📤 Development Requests Sent: {result['development_requests']}")
    print(f"✅ Successful Responses: {result['successful_responses']}")
    print(f"📊 Report Available: {result['report_path']}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())