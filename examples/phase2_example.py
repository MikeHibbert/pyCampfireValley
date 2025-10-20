"""
CampfireValley Phase 2 Features Example

This example demonstrates the advanced enterprise features introduced in Phase 2:
- VALI Security Services
- Justice System
- Specialist Campfires
- Advanced Routing
- Monitoring & Logging
- Configuration Management
- Hierarchical Storage
"""

import asyncio
import tempfile
from pathlib import Path

from campfirevalley import (
    Valley, Torch,
    # VALI Services
    VALICoordinator, ContentValidatorService, SignatureVerifierService,
    # Justice System
    JusticeSystem, PolicyRule, ViolationType, ActionType, Severity,
    # Specialist Campfires
    SanitizerCampfire, ValidatorCampfire, RouterCampfire,
    SanitizationLevel, ValidationMode, RoutingStrategy,
    # Advanced Routing
    AdvancedRoutingEngine, SmartLoadBalancer, LoadBalancingAlgorithm,
    # Monitoring
    MonitoringSystem, get_monitoring_system, record_metric, send_alert,
    # Configuration Management
    get_config_manager, ConfigEnvironment,
    # Hierarchical Storage
    create_hierarchical_party_box, StoragePolicy, CompressionType
)


async def demonstrate_vali_services():
    """Demonstrate VALI security services."""
    print("\n🛡️ VALI Services Demo")
    print("=" * 50)
    
    # Initialize VALI coordinator
    coordinator = VALICoordinator()
    
    # Register services
    content_validator = ContentValidatorService()
    signature_verifier = SignatureVerifierService()
    
    await coordinator.register_service(content_validator)
    await coordinator.register_service(signature_verifier)
    
    # Create test torch
    torch = Torch(
        id="vali_test_001",
        content={"message": "Hello from VALI!"},
        sender="TestSender",
        recipient="TestRecipient"
    )
    
    # Validate content
    validation_result = await coordinator.validate_content(torch)
    print(f"Content validation: {validation_result.is_valid}")
    
    # Verify signature (mock)
    signature_result = await coordinator.verify_signature(torch, "mock_signature")
    print(f"Signature verification: {signature_result.is_valid}")
    
    await coordinator.shutdown()


async def demonstrate_justice_system():
    """Demonstrate justice system with policy enforcement."""
    print("\n⚖️ Justice System Demo")
    print("=" * 50)
    
    # Initialize justice system
    justice = JusticeSystem()
    
    # Add policy rules
    rate_limit_rule = PolicyRule(
        id="rate_limit",
        name="Rate Limiting",
        violation_type=ViolationType.RATE_LIMIT,
        condition="requests_per_minute > 100",
        action_type=ActionType.THROTTLE,
        severity=Severity.MEDIUM,
        enabled=True
    )
    
    content_policy_rule = PolicyRule(
        id="content_policy",
        name="Content Policy",
        violation_type=ViolationType.CONTENT_VIOLATION,
        condition="contains_spam == true",
        action_type=ActionType.BLOCK,
        severity=Severity.HIGH,
        enabled=True
    )
    
    await justice.add_policy_rule(rate_limit_rule)
    await justice.add_policy_rule(content_policy_rule)
    
    # Create test torch
    torch = Torch(
        id="justice_test_001",
        content={"message": "This is a test message"},
        sender="TestSender",
        recipient="TestRecipient"
    )
    
    # Evaluate torch against policies
    decision = await justice.evaluate_torch(torch, {"requests_per_minute": 50})
    print(f"Justice decision: {decision.action}")
    print(f"Violations detected: {len(decision.violations)}")
    
    await justice.shutdown()


async def demonstrate_specialist_campfires():
    """Demonstrate specialist campfires."""
    print("\n🔧 Specialist Campfires Demo")
    print("=" * 50)
    
    # Initialize specialist campfires
    sanitizer = SanitizerCampfire(
        name="ContentSanitizer",
        sanitization_level=SanitizationLevel.AGGRESSIVE
    )
    
    validator = ValidatorCampfire(
        name="ContentValidator",
        validation_mode=ValidationMode.STRICT
    )
    
    router = RouterCampfire(
        name="IntelligentRouter",
        routing_strategy=RoutingStrategy.LOAD_BALANCED
    )
    
    # Start campfires
    await sanitizer.start()
    await validator.start()
    await router.start()
    
    # Create test torch
    torch = Torch(
        id="specialist_test_001",
        content={"message": "Test content with <script>alert('xss')</script>"},
        sender="TestSender",
        recipient="TestRecipient"
    )
    
    # Process through sanitizer
    sanitized_torch = await sanitizer.process_torch(torch)
    print(f"Sanitized content: {sanitized_torch.content}")
    
    # Process through validator
    validation_result = await validator.process_torch(sanitized_torch)
    print(f"Validation result: {validation_result.content.get('validation_status')}")
    
    # Process through router
    routing_result = await router.process_torch(validation_result)
    print(f"Routing decision: {routing_result.content.get('route_decision')}")
    
    # Stop campfires
    await sanitizer.stop()
    await validator.stop()
    await router.stop()


async def demonstrate_advanced_routing():
    """Demonstrate advanced routing capabilities."""
    print("\n🌐 Advanced Routing Demo")
    print("=" * 50)
    
    # Initialize routing engine
    routing_engine = AdvancedRoutingEngine()
    
    # Initialize load balancer
    load_balancer = SmartLoadBalancer(
        algorithm=LoadBalancingAlgorithm.WEIGHTED_ROUND_ROBIN
    )
    
    # Add some mock endpoints
    endpoints = [
        {"id": "endpoint1", "address": "valley1.example.com", "weight": 3},
        {"id": "endpoint2", "address": "valley2.example.com", "weight": 2},
        {"id": "endpoint3", "address": "valley3.example.com", "weight": 1}
    ]
    
    for endpoint in endpoints:
        await load_balancer.add_endpoint(
            endpoint["id"], 
            endpoint["address"], 
            weight=endpoint["weight"]
        )
    
    # Create test torch
    torch = Torch(
        id="routing_test_001",
        content={"message": "Route me intelligently!"},
        sender="TestSender",
        recipient="TestRecipient"
    )
    
    # Get routing decision
    selected_endpoint = await load_balancer.select_endpoint()
    print(f"Selected endpoint: {selected_endpoint}")
    
    # Get routing metrics
    metrics = await routing_engine.get_metrics()
    print(f"Routing metrics: {metrics}")


async def demonstrate_monitoring():
    """Demonstrate monitoring and logging capabilities."""
    print("\n📊 Monitoring & Logging Demo")
    print("=" * 50)
    
    # Get monitoring system
    monitoring = get_monitoring_system()
    
    # Record some metrics
    await record_metric("torch_processed", 1, {"campfire": "test"})
    await record_metric("processing_time", 150.5, {"operation": "sanitize"})
    await record_metric("memory_usage", 85.2, {"component": "valley"})
    
    # Send alerts
    await send_alert(
        "high_memory_usage",
        "Memory usage is above 80%",
        severity="warning",
        **{"memory_percent": 85.2}
    )
    
    # Get system health
    health_status = await monitoring.health_checker.check_system_health()
    print(f"System health: {health_status}")
    
    # Get performance metrics
    perf_metrics = await monitoring.performance_monitor.get_current_metrics()
    print(f"Performance metrics: {perf_metrics}")


async def demonstrate_configuration_management():
    """Demonstrate configuration management."""
    print("\n⚙️ Configuration Management Demo")
    print("=" * 50)
    
    # Get config manager
    config_manager = get_config_manager()
    
    # Load configuration for development environment
    await config_manager.load_config(
        source="config/development.yaml",
        environment=ConfigEnvironment.DEVELOPMENT
    )
    
    # Get configuration values
    valley_config = config_manager.get_config_value("valley")
    print(f"Valley configuration: {valley_config}")
    
    campfire_config = config_manager.get_config_value("campfire")
    print(f"Campfire configuration: {campfire_config}")
    
    # Demonstrate config override
    with config_manager.config_override("valley.max_campfires", 20):
        max_campfires = config_manager.get_config_value("valley.max_campfires")
        print(f"Overridden max campfires: {max_campfires}")
    
    # Value should be back to original
    max_campfires = config_manager.get_config_value("valley.max_campfires")
    print(f"Original max campfires: {max_campfires}")


async def demonstrate_hierarchical_storage():
    """Demonstrate hierarchical storage system."""
    print("\n💾 Hierarchical Storage Demo")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create storage policy
        policy = StoragePolicy(
            name="demo_policy",
            hot_retention_days=1,
            warm_retention_days=7,
            cold_retention_days=30,
            archive_retention_days=365,
            compression_threshold_mb=1,  # Compress files > 1MB
            compression_type=CompressionType.GZIP,
            deduplication_enabled=True,
            auto_tier_enabled=True
        )
        
        # Create hierarchical party box
        party_box = create_hierarchical_party_box(temp_dir, policy)
        
        # Create test torch
        torch = Torch(
            id="storage_test_001",
            content={"message": "Test hierarchical storage"},
            sender="TestSender",
            recipient="TestRecipient"
        )
        
        # Store attachments
        doc_data = b"Important document content" * 100  # ~2.7KB
        image_data = b"Binary image data" * 500  # ~8.5KB
        
        doc_id = await party_box.store_attachment(
            torch.id, "document.txt", doc_data
        )
        image_id = await party_box.store_attachment(
            torch.id, "image.jpg", image_data
        )
        
        print(f"Stored document: {doc_id}")
        print(f"Stored image: {image_id}")
        
        # List attachments
        attachments = await party_box.list_attachments(torch.id)
        print(f"Total attachments: {len(attachments)}")
        
        # Get storage statistics
        stats = await party_box.get_storage_stats()
        print(f"Storage stats: {stats}")
        
        # Optimize storage
        optimization_stats = await party_box.optimize_storage()
        print(f"Optimization results: {optimization_stats}")


async def demonstrate_complete_workflow():
    """Demonstrate a complete workflow using multiple Phase 2 features."""
    print("\n🚀 Complete Workflow Demo")
    print("=" * 50)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create valley with advanced configuration
        config_dir = Path(temp_dir) / "config"
        config_dir.mkdir()
        
        # Create a simple config file
        config_file = config_dir / "valley.yaml"
        config_file.write_text("""
valley:
  name: "DemoValley"
  max_campfires: 10
  enable_monitoring: true
  enable_justice: true

campfire:
  default_timeout: 30
  max_memory_mb: 512
""")
        
        # Initialize valley with config
        valley = Valley("DemoValley", config_dir=str(config_dir))
        
        # Start valley (this will load advanced config)
        await valley.start()
        
        # Create test torch
        torch = Torch(
            id="workflow_test_001",
            content={
                "message": "Complete workflow test",
                "priority": "high",
                "requires_validation": True
            },
            sender="WorkflowSender",
            recipient="WorkflowRecipient"
        )
        
        print(f"Processing torch: {torch.id}")
        print(f"Valley '{valley.name}' is running with advanced features")
        
        # The valley now has:
        # - Advanced configuration management
        # - Monitoring system
        # - Justice system (if enabled)
        # - Enhanced party box storage
        
        # Stop valley
        await valley.stop()
        print("Workflow completed successfully!")


async def main():
    """Run all Phase 2 feature demonstrations."""
    print("🎉 CampfireValley Phase 2 Features Demonstration")
    print("=" * 60)
    
    try:
        await demonstrate_vali_services()
        await demonstrate_justice_system()
        await demonstrate_specialist_campfires()
        await demonstrate_advanced_routing()
        await demonstrate_monitoring()
        await demonstrate_configuration_management()
        await demonstrate_hierarchical_storage()
        await demonstrate_complete_workflow()
        
        print("\n✅ All Phase 2 features demonstrated successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())