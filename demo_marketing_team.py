#!/usr/bin/env python3
"""
CampfireValley Marketing Team Demo
==================================

This script demonstrates a local marketing team that generates website ideas
and concepts, then sends them to a dockerized development team via MCP for implementation.

The marketing team consists of:
- Marketing Strategist: Market analysis and strategic planning
- Creative Director: Visual design and creative concepts
- UX Researcher: User experience and usability analysis
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import aiohttp
import requests
import yaml

from campfirevalley.valley import Valley
from campfirevalley.config_manager import ConfigManager
from campfirevalley.models import Torch


class MarketingTeamDemo:
    """Demo for the local marketing team that generates website ideas."""
    
    def __init__(self, config_path: str = "manifest.yaml", dev_team_url: str = "http://localhost:8080"):
        """Initialize the marketing team demo."""
        self.config_path = config_path
        self.dev_team_url = dev_team_url
        self.valley = None
        self.demo_results = {
            "marketing_ideas": [],
            "team_collaboration": {},
            "development_requests": [],
            "development_responses": []
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    async def initialize_valley(self):
        """Initialize the CampfireValley with marketing team configurations."""
        try:
            # Initialize Valley with proper parameters
            self.valley = Valley(
                name="marketing-team",
                manifest_path=self.config_path,
                config_dir="./config"
            )
            
            # Start the valley
            await self.valley.start()
            
            # Load marketing team campfires
            await self._load_marketing_campfires()
            
            self.logger.info("Marketing team valley initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize valley: {e}")
            raise
    
    async def _load_marketing_campfires(self):
        """Load the marketing team campfires from configuration files."""
        import yaml
        from pathlib import Path
        from campfirevalley.models import CampfireConfig
        
        campfire_names = ["marketing-strategist", "creative-director", "ux-researcher"]
        config_dir = Path("config/campfires")
        
        for campfire_name in campfire_names:
            try:
                config_file = config_dir / f"{campfire_name}.yaml"
                if not config_file.exists():
                    self.logger.error(f"Configuration file not found: {config_file}")
                    continue
                
                # Load YAML configuration
                with open(config_file, 'r') as f:
                    config_data = yaml.safe_load(f)
                
                # Create CampfireConfig
                campfire_config = CampfireConfig(
                    name=config_data['name'],
                    type=config_data.get('type', 'LLMCampfire'),
                    description=config_data.get('description', ''),
                    config=config_data
                )
                
                # Provision the campfire
                success = await self.valley.provision_campfire(campfire_config)
                if success:
                    self.logger.info(f"Successfully loaded campfire: {campfire_name}")
                else:
                    self.logger.error(f"Failed to provision campfire: {campfire_name}")
                    
            except Exception as e:
                self.logger.error(f"Error loading campfire {campfire_name}: {e}")
                continue
    
    async def generate_website_ideas(self) -> List[Dict[str, Any]]:
        """Generate website ideas through marketing team collaboration."""
        self.logger.info("Starting website idea generation process...")
        
        # Define website idea prompts
        idea_prompts = [
            {
                "category": "E-commerce Innovation",
                "prompt": "Generate a concept for an innovative e-commerce platform that addresses current market gaps and provides unique value to both buyers and sellers."
            },
            {
                "category": "SaaS Solution",
                "prompt": "Develop a SaaS platform concept that solves a specific business problem for small to medium enterprises, with clear monetization strategy."
            },
            {
                "category": "Community Platform",
                "prompt": "Create a community-driven platform concept that brings together people with shared interests or goals, fostering engagement and value creation."
            }
        ]
        
        website_ideas = []
        
        for idea_prompt in idea_prompts:
            self.logger.info(f"Generating idea for: {idea_prompt['category']}")
            
            # Step 1: Marketing Strategist develops strategic foundation
            strategy_request = Torch(
                claim="marketing_strategy_analysis",
                source_campfire="marketing-team-orchestrator",
                channel="marketing-strategy",
                torch_id=f"torch_strategy_{len(website_ideas) + 1}",
                sender_valley="marketing-team",
                target_address="marketing-team:marketing-strategist",
                signature="marketing_team_signature",
                source="marketing-team-orchestrator",
                destination="marketing-strategist",
                data={
                    "message": f"""
                    {idea_prompt['prompt']}
                    
                    Please provide a comprehensive strategic analysis including:
                    - Market opportunity and size
                    - Target audience definition
                    - Competitive landscape analysis
                    - Value proposition development
                    - Revenue model recommendations
                    - Go-to-market strategy
                    - Success metrics and KPIs
                    """,
                    "task_type": "website_ideation",
                    "category": idea_prompt['category']
                },
                metadata={"task_type": "website_ideation", "category": idea_prompt['category']}
            )
            
            strategy_response = await self.valley.process_torch(strategy_request)
            
            # Step 2: Creative Director develops visual and creative concepts
            creative_request = Torch(
                claim="creative_concept_development",
                source_campfire="marketing-team-orchestrator",
                channel="creative-design",
                torch_id=f"torch_creative_{len(website_ideas) + 1}",
                sender_valley="marketing-team",
                target_address="marketing-team:creative-director",
                signature="marketing_team_signature",
                source="marketing-team-orchestrator",
                destination="creative-director",
                data={
                    "message": f"""
                    Based on this strategic foundation: {strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else '')}
                    
                    Develop creative concepts for this website including:
                    - Visual identity and brand personality
                    - Design philosophy and principles
                    - User interface concept and interactions
                    - Visual hierarchy and information architecture
                    - Color palette and typography recommendations
                    - Creative differentiation strategies
                    - Emotional connection and user engagement approaches
                    """,
                    "task_type": "creative_development",
                    "category": idea_prompt['category'],
                    "strategy_input": strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else '')
                },
                metadata={
                    "task_type": "creative_development", 
                    "category": idea_prompt['category'],
                    "strategy_input": strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else '')
                }
            )
            
            creative_response = await self.valley.process_torch(creative_request)
            
            # Step 3: UX Researcher provides user experience analysis
            ux_request = Torch(
                claim="ux_research_analysis",
                source_campfire="marketing-team-orchestrator",
                channel="ux-research",
                torch_id=f"torch_ux_{len(website_ideas) + 1}",
                sender_valley="marketing-team",
                target_address="marketing-team:ux-researcher",
                signature="marketing_team_signature",
                source="marketing-team-orchestrator",
                destination="ux-researcher",
                data={
                    "message": f"""
                    Analyze this website concept from a user research perspective:
                    
                    Strategic Foundation: {strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else '')}
                    Creative Concept: {creative_response.data.get('message', creative_response.payload if hasattr(creative_response, 'payload') else '')}
                    
                    Provide user experience analysis including:
                    - User needs and pain point analysis
                    - Target user personas and characteristics
                    - User journey mapping and optimization
                    - Usability and accessibility considerations
                    - Information architecture recommendations
                    - User testing and validation strategies
                    - Success metrics for user experience
                    """,
                    "task_type": "user_research_analysis",
                    "category": idea_prompt['category'],
                    "strategy_input": strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else ''),
                    "creative_input": creative_response.data.get('message', creative_response.payload if hasattr(creative_response, 'payload') else '')
                },
                metadata={
                    "task_type": "user_research_analysis",
                    "category": idea_prompt['category'],
                    "strategy_input": strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else ''),
                    "creative_input": creative_response.data.get('message', creative_response.payload if hasattr(creative_response, 'payload') else '')
                }
            )
            
            ux_response = await self.valley.process_torch(ux_request)
            
            # Compile the complete website idea
            website_idea = {
                "id": f"idea_{len(website_ideas) + 1}",
                "category": idea_prompt['category'],
                "timestamp": datetime.now().isoformat(),
                "strategic_analysis": {
                    "content": strategy_response.data.get('message', strategy_response.payload if hasattr(strategy_response, 'payload') else ''),
                    "metadata": strategy_response.metadata
                },
                "creative_concept": {
                    "content": creative_response.data.get('message', creative_response.payload if hasattr(creative_response, 'payload') else ''),
                    "metadata": creative_response.metadata
                },
                "ux_analysis": {
                    "content": ux_response.data.get('message', ux_response.payload if hasattr(ux_response, 'payload') else ''),
                    "metadata": ux_response.metadata
                },
                "collaboration_summary": {
                    "team_members": ["marketing-strategist", "creative-director", "ux-researcher"],
                    "process_duration": "collaborative_ideation",
                    "quality_score": self._calculate_idea_quality_score(strategy_response, creative_response, ux_response)
                }
            }
            
            website_ideas.append(website_idea)
            self.logger.info(f"Completed idea generation for: {idea_prompt['category']}")
        
        self.demo_results["marketing_ideas"] = website_ideas
        self.logger.info(f"Generated {len(website_ideas)} website ideas")
        return website_ideas
    
    def _calculate_idea_quality_score(self, strategy_resp, creative_resp, ux_resp) -> float:
        """Calculate a quality score for the generated idea based on response quality."""
        # Simple scoring based on response length and completeness
        strategy_content = strategy_resp.data.get('message', strategy_resp.payload if hasattr(strategy_resp, 'payload') else '')
        creative_content = creative_resp.data.get('message', creative_resp.payload if hasattr(creative_resp, 'payload') else '')
        ux_content = ux_resp.data.get('message', ux_resp.payload if hasattr(ux_resp, 'payload') else '')
        
        strategy_score = min(len(strategy_content) / 1000, 1.0)
        creative_score = min(len(creative_content) / 1000, 1.0)
        ux_score = min(len(ux_content) / 1000, 1.0)
        
        return round((strategy_score + creative_score + ux_score) / 3 * 100, 1)
    
    async def check_development_team_health(self) -> bool:
        """Check if the development team server is healthy."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.dev_team_url}/health", timeout=5) as response:
                    if response.status == 200:
                        health_data = await response.json()
                        self.logger.info(f"Development team health check: {health_data}")
                        return True
                    else:
                        self.logger.warning(f"Development team health check failed: {response.status}")
                        return False
        except Exception as e:
            self.logger.error(f"Failed to connect to development team: {e}")
            return False
    
    async def send_ideas_to_development_team(self, website_ideas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Send website ideas to the dockerized development team via MCP."""
        self.logger.info("Sending website ideas to development team...")
        
        # Check if development team is healthy before sending ideas
        if not await self.check_development_team_health():
            self.logger.error("Development team is not healthy. Cannot send ideas.")
            return [{
                "idea_id": idea["id"],
                "status": "health_check_failed",
                "error": "Development team server is not responding",
                "response_time": "failed"
            } for idea in website_ideas]
        
        development_results = []
        
        for idea in website_ideas:
            try:
                # Prepare the idea for transmission to development team
                development_request = {
                    "idea_id": idea["id"],
                    "category": idea["category"],
                    "strategic_requirements": idea["strategic_analysis"]["content"],
                    "creative_requirements": idea["creative_concept"]["content"],
                    "ux_requirements": idea["ux_analysis"]["content"],
                    "timestamp": datetime.now().isoformat(),
                    "source_team": "marketing_team"
                }
                
                # Send to dockerized development team via HTTP/MCP
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.post(
                            f"{self.dev_team_url}/api/develop_website",
                            json=development_request,
                            timeout=aiohttp.ClientTimeout(total=120)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                development_results.append({
                                    "idea_id": idea["id"],
                                    "status": "success",
                                    "development_result": result,
                                    "response_time": result.get("processing_time", "unknown")
                                })
                                self.logger.info(f"Successfully sent idea {idea['id']} to development team")
                            else:
                                error_text = await response.text()
                                development_results.append({
                                    "idea_id": idea["id"],
                                    "status": "error",
                                    "error": f"HTTP {response.status}: {error_text}",
                                    "response_time": "failed"
                                })
                                self.logger.error(f"Failed to send idea {idea['id']}: HTTP {response.status}")
                    
                    except asyncio.TimeoutError:
                        development_results.append({
                            "idea_id": idea["id"],
                            "status": "timeout",
                            "error": "Request timed out after 120 seconds",
                            "response_time": "timeout"
                        })
                        self.logger.error(f"Timeout sending idea {idea['id']} to development team")
                    
                    except aiohttp.ClientError as e:
                        development_results.append({
                            "idea_id": idea["id"],
                            "status": "connection_error",
                            "error": f"Connection error: {str(e)}",
                            "response_time": "failed"
                        })
                        self.logger.error(f"Connection error sending idea {idea['id']}: {e}")
            
            except Exception as e:
                development_results.append({
                    "idea_id": idea["id"],
                    "status": "error",
                    "error": f"Unexpected error: {str(e)}",
                    "response_time": "failed"
                })
                self.logger.error(f"Unexpected error processing idea {idea['id']}: {e}")
        
        self.demo_results["development_requests"] = development_results
        self.demo_results["development_responses"] = [r for r in development_results if r["status"] == "success"]
        return development_results
    
    async def generate_marketing_report(self) -> str:
        """Generate an HTML report of the marketing team's work."""
        self.logger.info("Generating marketing team report...")
        
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "team_composition": ["Marketing Strategist", "Creative Director", "UX Researcher"],
            "ideas_generated": len(self.demo_results.get("marketing_ideas", [])),
            "development_requests_sent": len(self.demo_results.get("development_requests", [])),
            "demo_results": self.demo_results
        }
        
        html_content = self._generate_marketing_html_report(report_data)
        
        # Save the report
        report_path = Path("marketing_team_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        self.logger.info(f"Marketing team report saved to: {report_path}")
        return str(report_path)
    
    def _generate_marketing_html_report(self, report_data: Dict[str, Any]) -> str:
        """Generate HTML content for the marketing team report."""
        website_ideas = report_data["demo_results"].get("marketing_ideas", [])
        development_requests = report_data["demo_results"].get("development_requests", [])
        
        ideas_html = ""
        for idea in website_ideas:
            ideas_html += f"""
            <div class="idea-card">
                <h3>{idea['category']} (ID: {idea['id']})</h3>
                <div class="idea-section">
                    <h4>Strategic Analysis</h4>
                    <div class="content-box">{idea['strategic_analysis']['content'][:500]}...</div>
                </div>
                <div class="idea-section">
                    <h4>Creative Concept</h4>
                    <div class="content-box">{idea['creative_concept']['content'][:500]}...</div>
                </div>
                <div class="idea-section">
                    <h4>UX Analysis</h4>
                    <div class="content-box">{idea['ux_analysis']['content'][:500]}...</div>
                </div>
                <div class="quality-score">Quality Score: {idea['collaboration_summary']['quality_score']}%</div>
            </div>
            """
        
        requests_html = ""
        for req in development_requests:
            status_class = "success" if req["status"] == "success" else "error"
            requests_html += f"""
            <div class="request-card {status_class}">
                <h4>Idea {req['idea_id']}</h4>
                <p><strong>Status:</strong> {req['status']}</p>
                <p><strong>Response Time:</strong> {req['response_time']}</p>
                {f"<p><strong>Error:</strong> {req.get('error', '')}</p>" if req['status'] != 'success' else ''}
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CampfireValley Marketing Team Report</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f7fa; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; }}
                .header h1 {{ margin: 0; font-size: 2.5em; }}
                .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
                .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 30px; }}
                .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #667eea; }}
                .stat-number {{ font-size: 2em; font-weight: bold; color: #667eea; }}
                .stat-label {{ color: #6c757d; margin-top: 5px; }}
                .section {{ padding: 30px; border-top: 1px solid #e9ecef; }}
                .section h2 {{ color: #495057; margin-bottom: 20px; }}
                .idea-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px; border-left: 4px solid #28a745; }}
                .idea-section {{ margin-bottom: 15px; }}
                .idea-section h4 {{ color: #495057; margin-bottom: 8px; }}
                .content-box {{ background: white; padding: 15px; border-radius: 5px; border: 1px solid #dee2e6; font-size: 0.9em; line-height: 1.5; }}
                .quality-score {{ text-align: right; font-weight: bold; color: #28a745; }}
                .request-card {{ background: #f8f9fa; border-radius: 8px; padding: 15px; margin-bottom: 10px; }}
                .request-card.success {{ border-left: 4px solid #28a745; }}
                .request-card.error {{ border-left: 4px solid #dc3545; }}
                .timestamp {{ text-align: center; padding: 20px; color: #6c757d; font-size: 0.9em; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔥 CampfireValley Marketing Team Report</h1>
                    <p>Website Idea Generation & Development Collaboration</p>
                    <p>Generated: {report_data['timestamp']}</p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{report_data['ideas_generated']}</div>
                        <div class="stat-label">Website Ideas Generated</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{len(report_data['team_composition'])}</div>
                        <div class="stat-label">Team Members</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{report_data['development_requests_sent']}</div>
                        <div class="stat-label">Development Requests</div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Generated Website Ideas</h2>
                    {ideas_html}
                </div>
                
                <div class="section">
                    <h2>Development Team Collaboration</h2>
                    {requests_html}
                </div>
                
                <div class="timestamp">
                    Report generated by CampfireValley Marketing Team Demo
                </div>
            </div>
        </body>
        </html>
        """
    
    async def run_demo(self):
        """Run the complete marketing team demo."""
        try:
            self.logger.info("Starting CampfireValley Marketing Team Demo...")
            
            # Initialize the valley
            await self.initialize_valley()
            
            # Generate website ideas
            website_ideas = await self.generate_website_ideas()
            
            # Send ideas to development team
            development_results = await self.send_ideas_to_development_team(website_ideas)
            
            # Generate report
            report_path = await self.generate_marketing_report()
            
            self.logger.info("Marketing team demo completed successfully!")
            self.logger.info(f"Report available at: {report_path}")
            
            return {
                "status": "success",
                "website_ideas": len(website_ideas),
                "development_requests": len(development_results),
                "report_path": report_path,
                "results": self.demo_results
            }
            
        except Exception as e:
            self.logger.error(f"Demo failed: {e}")
            raise


async def main():
    """Main entry point for the marketing team demo."""
    demo = MarketingTeamDemo()
    result = await demo.run_demo()
    
    print("\n" + "="*60)
    print("🔥 CAMPFIREVALLEY MARKETING TEAM DEMO COMPLETE")
    print("="*60)
    print(f"✅ Website Ideas Generated: {result['website_ideas']}")
    print(f"📤 Development Requests Sent: {result['development_requests']}")
    print(f"📊 Report Available: {result['report_path']}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())