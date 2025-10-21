"""
Default Dock Campfires Demo

This demo showcases the three default dock campfires in CampfireValley:
1. DockmasterCampfire - Handles torch loading, routing, and packing
2. SanitizerCampfire - Provides content security and sanitization
3. JusticeCampfire - Manages governance, compliance, and violations

Each campfire contains specialized campers that work together to provide
comprehensive valley dock functionality.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List

from campfirevalley.models import Torch, CampfireConfig
from campfirevalley.mcp import RedisMCPBroker
from campfirevalley.campfires import (
    DockmasterCampfire, SanitizerCampfire, JusticeCampfire,
    SanitizationLevel, ViolationType, SanctionType, PolicyRule
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DockCampfiresDemo:
    """
    Demonstrates the functionality of default dock campfires.
    """
    
    def __init__(self):
        """Initialize the demo with MCP broker and campfires."""
        self.mcp_broker = None
        self.dockmaster = None
        self.sanitizer = None
        self.justice = None
        
        # Demo data
        self.demo_torches = []
        self.demo_results = {
            'dockmaster': [],
            'sanitizer': [],
            'justice': []
        }
    
    async def setup(self):
        """Set up the demo environment."""
        logger.info("Setting up Dock Campfires Demo...")
        
        # Initialize MCP broker
        self.mcp_broker = RedisMCPBroker(
            host='localhost',
            port=6379,
            valley_name='DemoValley'
        )
        await self.mcp_broker.connect()
        
        # Initialize campfires
        self.dockmaster = DockmasterCampfire(self.mcp_broker)
        self.sanitizer = SanitizerCampfire(self.mcp_broker)
        self.justice = JusticeCampfire(self.mcp_broker)
        
        # Start all campfires
        await self.dockmaster.start()
        await self.sanitizer.start()
        await self.justice.start()
        
        # Create demo torches
        self._create_demo_torches()
        
        logger.info("Demo setup completed!")
    
    async def cleanup(self):
        """Clean up demo resources."""
        logger.info("Cleaning up demo resources...")
        
        if self.dockmaster:
            await self.dockmaster.stop()
        if self.sanitizer:
            await self.sanitizer.stop()
        if self.justice:
            await self.justice.stop()
        if self.mcp_broker:
            await self.mcp_broker.disconnect()
        
        logger.info("Cleanup completed!")
    
    def _create_demo_torches(self):
        """Create various demo torches for testing."""
        self.demo_torches = [
            # Clean torch
            Torch(
                id="torch_001",
                sender_valley="TechValley",
                target_address="CreativeValley/design",
                payload={
                    "type": "collaboration_request",
                    "message": "Hello! We'd like to collaborate on a new UI design.",
                    "project": "NextGen App",
                    "priority": "normal"
                },
                attachments=[],
                signature="valid_signature_123",
                timestamp=datetime.utcnow()
            ),
            
            # Torch with potential security issues
            Torch(
                id="torch_002",
                sender_valley="UnknownValley",
                target_address="BusinessValley/strategy",
                payload={
                    "type": "suspicious_content",
                    "message": "<script>alert('malicious')</script>This looks suspicious",
                    "data": "javascript:void(0)",
                    "priority": "high"
                },
                attachments=[],
                signature="",
                timestamp=datetime.utcnow()
            ),
            
            # Torch with policy violations
            Torch(
                id="torch_003",
                sender_valley="SpamValley",
                target_address="TechValley/general",
                payload={
                    "type": "spam_content",
                    "message": "spam " * 1000,  # Very long spam message
                    "inappropriate": "This contains inappropriate content",
                    "priority": "urgent"
                },
                attachments=[],
                signature="invalid_signature",
                timestamp=datetime.utcnow()
            ),
            
            # Large torch for testing routing
            Torch(
                id="torch_004",
                sender_valley="DataValley",
                target_address="BusinessValley/analytics",
                payload={
                    "type": "data_transfer",
                    "message": "Large dataset transfer",
                    "data": {"records": list(range(1000))},  # Large payload
                    "priority": "low"
                },
                attachments=["large_dataset.csv", "analysis_report.pdf"],
                signature="valid_signature_456",
                timestamp=datetime.utcnow()
            )
        ]
    
    async def demo_dockmaster_campfire(self):
        """Demonstrate Dockmaster campfire functionality."""
        logger.info("\n" + "="*60)
        logger.info("DOCKMASTER CAMPFIRE DEMO")
        logger.info("="*60)
        
        logger.info("Dockmaster handles torch loading, routing, and packing...")
        
        for torch in self.demo_torches:
            logger.info(f"\nProcessing torch {torch.id} through Dockmaster...")
            
            try:
                # Process torch through dockmaster
                processed_torch = await self.dockmaster.process_torch(torch)
                
                if processed_torch:
                    result = {
                        'torch_id': torch.id,
                        'status': 'processed',
                        'original_size': len(json.dumps(torch.payload)),
                        'processed_size': len(json.dumps(processed_torch.payload)),
                        'routing_info': {
                            'sender': torch.sender_valley,
                            'target': torch.target_address,
                            'attachments': len(torch.attachments)
                        }
                    }
                    
                    logger.info(f"✅ Torch {torch.id} successfully processed by Dockmaster")
                    logger.info(f"   Original size: {result['original_size']} bytes")
                    logger.info(f"   Processed size: {result['processed_size']} bytes")
                    logger.info(f"   Route: {torch.sender_valley} → {torch.target_address}")
                    
                else:
                    result = {
                        'torch_id': torch.id,
                        'status': 'failed',
                        'reason': 'Processing failed'
                    }
                    logger.warning(f"❌ Torch {torch.id} failed processing by Dockmaster")
                
                self.demo_results['dockmaster'].append(result)
                
            except Exception as e:
                logger.error(f"❌ Error processing torch {torch.id}: {e}")
                self.demo_results['dockmaster'].append({
                    'torch_id': torch.id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Show dockmaster campers info
        campers = self.dockmaster.get_campers()
        logger.info(f"\nDockmaster active campers: {list(campers.keys())}")
        
        logger.info("\nDockmaster demo completed!")
    
    async def demo_sanitizer_campfire(self):
        """Demonstrate Sanitizer campfire functionality."""
        logger.info("\n" + "="*60)
        logger.info("SANITIZER CAMPFIRE DEMO")
        logger.info("="*60)
        
        logger.info("Sanitizer handles content security, filtering, and quarantine...")
        
        for torch in self.demo_torches:
            logger.info(f"\nProcessing torch {torch.id} through Sanitizer...")
            
            try:
                # Process torch through sanitizer
                processed_torch = await self.sanitizer.process_torch(torch)
                
                if processed_torch:
                    result = {
                        'torch_id': torch.id,
                        'status': 'sanitized',
                        'content_modified': processed_torch.payload != torch.payload,
                        'security_check': 'passed'
                    }
                    
                    logger.info(f"✅ Torch {torch.id} passed sanitization")
                    if result['content_modified']:
                        logger.info(f"   Content was sanitized for security")
                    else:
                        logger.info(f"   Content was clean, no changes needed")
                    
                elif processed_torch is None:
                    result = {
                        'torch_id': torch.id,
                        'status': 'quarantined',
                        'reason': 'Security threat detected'
                    }
                    logger.warning(f"🔒 Torch {torch.id} quarantined due to security threats")
                
                self.demo_results['sanitizer'].append(result)
                
            except Exception as e:
                logger.error(f"❌ Error sanitizing torch {torch.id}: {e}")
                self.demo_results['sanitizer'].append({
                    'torch_id': torch.id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Show sanitizer statistics
        quarantine_stats = await self.sanitizer.get_quarantine_stats()
        logger.info(f"\nQuarantine statistics: {quarantine_stats}")
        
        # Show sanitizer campers info
        campers = self.sanitizer.get_campers()
        logger.info(f"Sanitizer active campers: {list(campers.keys())}")
        
        logger.info("\nSanitizer demo completed!")
    
    async def demo_justice_campfire(self):
        """Demonstrate Justice campfire functionality."""
        logger.info("\n" + "="*60)
        logger.info("JUSTICE CAMPFIRE DEMO")
        logger.info("="*60)
        
        logger.info("Justice handles governance, compliance, and violation management...")
        
        # Add a custom policy rule for demo
        custom_rule = PolicyRule(
            id="demo_policy_001",
            name="Demo Content Policy",
            description="Detects demo-specific policy violations",
            violation_type=ViolationType.CONTENT_POLICY,
            severity=6,
            auto_enforce=True,
            sanction=SanctionType.WARNING
        )
        await self.justice.add_policy_rule(custom_rule)
        logger.info(f"Added custom policy rule: {custom_rule.name}")
        
        for torch in self.demo_torches:
            logger.info(f"\nProcessing torch {torch.id} through Justice...")
            
            try:
                # Process torch through justice
                processed_torch = await self.justice.process_torch(torch)
                
                if processed_torch:
                    result = {
                        'torch_id': torch.id,
                        'status': 'approved',
                        'governance_check': 'passed'
                    }
                    
                    logger.info(f"✅ Torch {torch.id} passed governance checks")
                    
                elif processed_torch is None:
                    result = {
                        'torch_id': torch.id,
                        'status': 'blocked',
                        'reason': 'Policy violation detected'
                    }
                    logger.warning(f"🚫 Torch {torch.id} blocked due to policy violations")
                
                # Detect violations for demonstration
                violations = await self.justice.detect_violations(torch.payload)
                if violations:
                    result['violations'] = len(violations)
                    logger.info(f"   Detected {len(violations)} policy violations")
                    
                    # Apply sanctions for high-severity violations
                    for violation in violations:
                        if violation.get('severity', 0) >= 7:
                            sanction_result = await self.justice.apply_sanction(
                                violation, 
                                SanctionType.TEMPORARY_RESTRICTION,
                                timedelta(hours=1)
                            )
                            logger.info(f"   Applied sanction: {sanction_result['sanction_type']}")
                
                self.demo_results['justice'].append(result)
                
            except Exception as e:
                logger.error(f"❌ Error processing torch {torch.id} through justice: {e}")
                self.demo_results['justice'].append({
                    'torch_id': torch.id,
                    'status': 'error',
                    'error': str(e)
                })
        
        # Show governance report
        governance_report = await self.justice.get_governance_report()
        logger.info(f"\nGovernance report: {governance_report}")
        
        # Show justice campers info
        campers = self.justice.get_campers()
        logger.info(f"Justice active campers: {list(campers.keys())}")
        
        logger.info("\nJustice demo completed!")
    
    async def demo_integrated_pipeline(self):
        """Demonstrate integrated pipeline with all three campfires."""
        logger.info("\n" + "="*60)
        logger.info("INTEGRATED PIPELINE DEMO")
        logger.info("="*60)
        
        logger.info("Processing torches through complete dock pipeline...")
        logger.info("Pipeline: Dockmaster → Sanitizer → Justice")
        
        for torch in self.demo_torches:
            logger.info(f"\nProcessing torch {torch.id} through integrated pipeline...")
            
            try:
                current_torch = torch
                pipeline_results = []
                
                # Step 1: Dockmaster
                logger.info(f"  Step 1: Dockmaster processing...")
                current_torch = await self.dockmaster.process_torch(current_torch)
                if current_torch:
                    pipeline_results.append("dockmaster_passed")
                    logger.info(f"    ✅ Dockmaster: PASSED")
                else:
                    pipeline_results.append("dockmaster_failed")
                    logger.info(f"    ❌ Dockmaster: FAILED")
                    continue
                
                # Step 2: Sanitizer
                logger.info(f"  Step 2: Sanitizer processing...")
                current_torch = await self.sanitizer.process_torch(current_torch)
                if current_torch:
                    pipeline_results.append("sanitizer_passed")
                    logger.info(f"    ✅ Sanitizer: PASSED")
                else:
                    pipeline_results.append("sanitizer_quarantined")
                    logger.info(f"    🔒 Sanitizer: QUARANTINED")
                    continue
                
                # Step 3: Justice
                logger.info(f"  Step 3: Justice processing...")
                current_torch = await self.justice.process_torch(current_torch)
                if current_torch:
                    pipeline_results.append("justice_approved")
                    logger.info(f"    ✅ Justice: APPROVED")
                else:
                    pipeline_results.append("justice_blocked")
                    logger.info(f"    🚫 Justice: BLOCKED")
                    continue
                
                # Final result
                if current_torch:
                    logger.info(f"  🎉 Torch {torch.id} successfully completed the pipeline!")
                    logger.info(f"     Pipeline steps: {' → '.join(pipeline_results)}")
                
            except Exception as e:
                logger.error(f"❌ Pipeline error for torch {torch.id}: {e}")
        
        logger.info("\nIntegrated pipeline demo completed!")
    
    def print_demo_summary(self):
        """Print a summary of all demo results."""
        logger.info("\n" + "="*60)
        logger.info("DEMO SUMMARY")
        logger.info("="*60)
        
        # Dockmaster summary
        dockmaster_results = self.demo_results['dockmaster']
        dockmaster_processed = len([r for r in dockmaster_results if r['status'] == 'processed'])
        logger.info(f"Dockmaster: {dockmaster_processed}/{len(dockmaster_results)} torches processed")
        
        # Sanitizer summary
        sanitizer_results = self.demo_results['sanitizer']
        sanitizer_passed = len([r for r in sanitizer_results if r['status'] == 'sanitized'])
        sanitizer_quarantined = len([r for r in sanitizer_results if r['status'] == 'quarantined'])
        logger.info(f"Sanitizer: {sanitizer_passed} passed, {sanitizer_quarantined} quarantined")
        
        # Justice summary
        justice_results = self.demo_results['justice']
        justice_approved = len([r for r in justice_results if r['status'] == 'approved'])
        justice_blocked = len([r for r in justice_results if r['status'] == 'blocked'])
        logger.info(f"Justice: {justice_approved} approved, {justice_blocked} blocked")
        
        logger.info("\nDemo completed successfully! 🎉")
        logger.info("The default dock campfires are working together to provide:")
        logger.info("  • Efficient torch processing (Dockmaster)")
        logger.info("  • Content security and sanitization (Sanitizer)")
        logger.info("  • Governance and compliance (Justice)")


async def main():
    """Run the dock campfires demo."""
    demo = DockCampfiresDemo()
    
    try:
        await demo.setup()
        
        # Run individual campfire demos
        await demo.demo_dockmaster_campfire()
        await demo.demo_sanitizer_campfire()
        await demo.demo_justice_campfire()
        
        # Run integrated pipeline demo
        await demo.demo_integrated_pipeline()
        
        # Print summary
        demo.print_demo_summary()
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise
    finally:
        await demo.cleanup()


if __name__ == "__main__":
    print("🔥 CampfireValley - Default Dock Campfires Demo 🔥")
    print("=" * 60)
    print("This demo showcases the three default dock campfires:")
    print("1. DockmasterCampfire - Torch processing and routing")
    print("2. SanitizerCampfire - Content security and sanitization")
    print("3. JusticeCampfire - Governance and compliance")
    print("=" * 60)
    
    asyncio.run(main())