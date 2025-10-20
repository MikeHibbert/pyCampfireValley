#!/usr/bin/env python3
"""
Local Demo Orchestrator for CampfireValley
Runs both marketing and development teams locally without Docker
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import subprocess
import signal
import sys
import aiohttp

from demo_marketing_team import MarketingTeamDemo
from development_team_server import DevelopmentTeamServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class LocalDemoOrchestrator:
    """Orchestrates a local demo with both marketing and development teams."""
    
    def __init__(self, dev_team_port: int = 8080, reports_dir: str = "reports"):
        self.dev_team_port = dev_team_port
        self.dev_team_url = f"http://localhost:{dev_team_port}"
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(exist_ok=True)
        
        self.marketing_demo = MarketingTeamDemo(dev_team_url=self.dev_team_url)
        self.dev_team_server = None
        self.dev_server_task = None
        
        self.logger = logging.getLogger(__name__)
    
    async def start_development_team(self) -> bool:
        """Start the development team server locally."""
        try:
            self.logger.info("Starting local development team server...")
            
            # Initialize the development team server
            self.dev_team_server = DevelopmentTeamServer()
            await self.dev_team_server.initialize_valley()
            
            # Start the server in a background task
            self.dev_server_task = asyncio.create_task(
                self.dev_team_server.start_server(host="localhost", port=self.dev_team_port)
            )
            
            # Wait a moment for the server to start
            await asyncio.sleep(2)
            
            # Check if server is running
            if await self._check_dev_team_health():
                self.logger.info("Development team server started successfully")
                return True
            else:
                self.logger.error("Development team server failed to start properly")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start development team server: {e}")
            return False
    
    async def stop_development_team(self):
        """Stop the development team server."""
        try:
            if self.dev_server_task and not self.dev_server_task.done():
                self.dev_server_task.cancel()
                try:
                    await self.dev_server_task
                except asyncio.CancelledError:
                    pass
            self.logger.info("Development team server stopped")
        except Exception as e:
            self.logger.error(f"Error stopping development team server: {e}")
    
    async def _check_dev_team_health(self) -> bool:
        """Check if the development team server is healthy."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.dev_team_url}/health", timeout=5) as response:
                    return response.status == 200
        except Exception:
            return False
    
    async def wait_for_dev_team_ready(self, max_wait: int = 30) -> bool:
        """Wait for the development team to be ready."""
        self.logger.info("Waiting for development team to be ready...")
        
        for i in range(max_wait):
            if await self._check_dev_team_health():
                self.logger.info("Development team is ready!")
                return True
            await asyncio.sleep(1)
        
        self.logger.error("Development team failed to become ready")
        return False
    
    async def run_marketing_demo(self) -> Dict[str, Any]:
        """Run the marketing team demo."""
        self.logger.info("Running marketing team demo...")
        return await self.marketing_demo.run_demo()
    
    async def get_dev_team_results(self) -> Dict[str, Any]:
        """Get results from the development team."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.dev_team_url}/results") as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"error": f"Failed to get results: {response.status}"}
        except Exception as e:
            return {"error": f"Failed to connect to development team: {e}"}
    
    async def generate_comprehensive_report(self, marketing_results: Dict[str, Any], 
                                          dev_results: Dict[str, Any]) -> str:
        """Generate a comprehensive HTML report combining both teams."""
        timestamp = datetime.now().isoformat()
        
        # Extract key metrics
        marketing_ideas = marketing_results.get('demo_results', {}).get('marketing_ideas', [])
        dev_requests = marketing_results.get('demo_results', {}).get('development_requests', [])
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>CampfireValley Distributed Demo Report</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); color: white; padding: 40px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 2.5em; font-weight: 300; }}
                .header p {{ margin: 10px 0 0 0; opacity: 0.9; font-size: 1.1em; }}
                .section {{ padding: 30px; border-bottom: 1px solid #eee; }}
                .section:last-child {{ border-bottom: none; }}
                .section h2 {{ color: #2c3e50; margin-bottom: 20px; font-size: 1.8em; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
                .metric {{ background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center; border-left: 4px solid #3498db; }}
                .metric h3 {{ margin: 0 0 10px 0; color: #2c3e50; }}
                .metric .value {{ font-size: 2em; font-weight: bold; color: #3498db; }}
                .idea-card {{ background: #f8f9fa; margin: 15px 0; padding: 20px; border-radius: 10px; border-left: 4px solid #e74c3c; }}
                .idea-card h4 {{ margin: 0 0 10px 0; color: #2c3e50; }}
                .team-section {{ background: #ecf0f1; margin: 20px 0; padding: 20px; border-radius: 10px; }}
                .status-success {{ color: #27ae60; font-weight: bold; }}
                .status-error {{ color: #e74c3c; font-weight: bold; }}
                .json-display {{ background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 5px; font-family: 'Courier New', monospace; font-size: 0.9em; overflow-x: auto; }}
                .footer {{ background: #34495e; color: white; padding: 20px; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔥 CampfireValley Local Demo Report</h1>
                    <p>Comprehensive analysis of marketing and development team collaboration</p>
                    <p>Generated: {timestamp}</p>
                </div>
                
                <div class="section">
                    <h2>📊 Demo Overview</h2>
                    <div class="metrics">
                        <div class="metric">
                            <h3>Marketing Ideas</h3>
                            <div class="value">{len(marketing_ideas)}</div>
                        </div>
                        <div class="metric">
                            <h3>Development Requests</h3>
                            <div class="value">{len(dev_requests)}</div>
                        </div>
                        <div class="metric">
                            <h3>Teams Involved</h3>
                            <div class="value">2</div>
                        </div>
                        <div class="metric">
                            <h3>Communication Method</h3>
                            <div class="value">Local</div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>🎯 Marketing Team Results</h2>
                    <div class="team-section">
                        <h3>Generated Website Ideas</h3>
        """
        
        # Add marketing ideas
        for i, idea in enumerate(marketing_ideas, 1):
            html_content += f"""
                        <div class="idea-card">
                            <h4>Idea {i}: {idea.get('category', 'Unknown Category')}</h4>
                            <p><strong>Strategic Analysis:</strong> {idea.get('strategic_analysis', 'N/A')[:200]}...</p>
                            <p><strong>Creative Concept:</strong> {idea.get('creative_concept', 'N/A')[:200]}...</p>
                            <p><strong>UX Analysis:</strong> {idea.get('ux_analysis', 'N/A')[:200]}...</p>
                        </div>
            """
        
        html_content += """
                    </div>
                </div>
                
                <div class="section">
                    <h2>⚙️ Development Team Results</h2>
                    <div class="team-section">
        """
        
        if 'error' in dev_results:
            html_content += f"""
                        <p class="status-error">❌ Development Team Status: Error</p>
                        <p>Error: {dev_results['error']}</p>
            """
        else:
            html_content += f"""
                        <p class="status-success">✅ Development Team Status: Active</p>
                        <div class="json-display">
                            {json.dumps(dev_results, indent=2)}
                        </div>
            """
        
        html_content += f"""
                    </div>
                </div>
                
                <div class="section">
                    <h2>🔄 Inter-Team Communication</h2>
                    <div class="team-section">
                        <h3>Development Requests Sent</h3>
        """
        
        # Add development requests
        for i, request in enumerate(dev_requests, 1):
            status = request.get('status', 'unknown')
            status_class = 'status-success' if status == 'success' else 'status-error'
            html_content += f"""
                        <div class="idea-card">
                            <h4>Request {i}: {request.get('idea_id', 'Unknown ID')}</h4>
                            <p><strong>Status:</strong> <span class="{status_class}">{status}</span></p>
                            <p><strong>Category:</strong> {request.get('category', 'N/A')}</p>
                            <p><strong>Processing Time:</strong> {request.get('processing_time', 'N/A')} seconds</p>
                        </div>
            """
        
        html_content += f"""
                    </div>
                </div>
                
                <div class="section">
                    <h2>📈 Technical Details</h2>
                    <div class="team-section">
                        <h3>Marketing Team Configuration</h3>
                        <div class="json-display">
                            {json.dumps(marketing_results.get('team_info', {}), indent=2)}
                        </div>
                        
                        <h3>Full Marketing Results</h3>
                        <div class="json-display">
                            {json.dumps(marketing_results, indent=2)}
                        </div>
                    </div>
                </div>
                
                <div class="footer">
                    <p>🔥 Powered by CampfireValley - Distributed AI Team Collaboration Platform</p>
                    <p>Report generated at {timestamp}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    async def run_demo(self) -> Dict[str, Any]:
        """Run the complete local demo."""
        start_time = time.time()
        
        try:
            print("🔥 Starting Local CampfireValley Demo...")
            print("=" * 60)
            
            # Start development team
            if not await self.start_development_team():
                return {
                    "status": "error",
                    "error": "Failed to start development team",
                    "duration": time.time() - start_time
                }
            
            # Wait for development team to be ready
            if not await self.wait_for_dev_team_ready():
                return {
                    "status": "error", 
                    "error": "Development team not ready",
                    "duration": time.time() - start_time
                }
            
            # Run marketing demo
            marketing_results = await self.run_marketing_demo()
            
            # Get development team results
            dev_results = await self.get_dev_team_results()
            
            # Generate comprehensive report
            report_html = await self.generate_comprehensive_report(marketing_results, dev_results)
            
            # Save report
            report_path = self.reports_dir / f"local_demo_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_html)
            
            duration = time.time() - start_time
            
            return {
                "status": "success",
                "duration": duration,
                "marketing_results": marketing_results,
                "development_results": dev_results,
                "report_path": str(report_path),
                "teams_involved": ["marketing", "development"],
                "communication_method": "local"
            }
            
        except Exception as e:
            self.logger.error(f"Demo failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "duration": time.time() - start_time
            }
        
        finally:
            # Clean up
            await self.stop_development_team()

async def main():
    """Main function to run the local demo."""
    orchestrator = LocalDemoOrchestrator()
    
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        print("\n🛑 Received interrupt signal. Shutting down gracefully...")
        asyncio.create_task(orchestrator.stop_development_team())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        results = await orchestrator.run_demo()
        
        print("\n" + "=" * 60)
        print("📊 Demo Results:")
        print(f"Status: {results['status']}")
        
        if results['status'] == 'success':
            print(f"Duration: {results['duration']:.2f} seconds")
            print(f"Report saved to: {results['report_path']}")
            print(f"Teams involved: {', '.join(results['teams_involved'])}")
        else:
            print(f"Error: {results.get('error', 'Unknown error')}")
        
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n🛑 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())