"""
Sanitizer Campfire - Content security and sanitization functionality.

The Sanitizer campfire provides three essential campers:
- ScannerCamper: Scans content for security threats and policy violations
- FilterCamper: Filters and sanitizes unsafe content
- QuarantineCamper: Manages quarantined content and review processes
"""

import asyncio
import logging
import re
import html
import hashlib
import json
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field

from ..interfaces import ICampfire, IMCPBroker, ISanitizerCampfire
from ..models import Torch, CampfireConfig, ScanResult, SecurityLevel
from ..campfire import Campfire, ICamper
from ..vali import VALICoordinator, VALIServiceType
from ..security_scanner import EnhancedSecurityScanner, ThreatLevel, ScanEngine


logger = logging.getLogger(__name__)


class SanitizationLevel(Enum):
    """Content sanitization levels"""
    PERMISSIVE = "permissive"
    STANDARD = "standard"
    STRICT = "strict"
    AGGRESSIVE = "aggressive"


@dataclass
class SanitizationRule:
    """Defines a content sanitization rule"""
    name: str
    pattern: str
    replacement: str
    enabled: bool = True
    severity: ThreatLevel = ThreatLevel.LOW
    description: str = ""


@dataclass
class QuarantineItem:
    """Represents an item in quarantine"""
    id: str
    content: Dict[str, Any]
    reason: str
    quarantined_at: datetime
    torch_id: str
    sender_valley: str
    review_status: str = "pending"  # pending, approved, rejected
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class ScannerCamper(ICamper):
    """
    Scanner camper handles content security scanning and threat detection.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Scanner camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.scan_engines = config.get('scan_engines', ['MALWARE_DETECTOR', 'XSS_DETECTOR'])
        self.threat_threshold = ThreatLevel(config.get('threat_threshold', 'MEDIUM'))
        self.vali_coordinator = None
        self.security_scanner = EnhancedSecurityScanner()
        self._running = False
        
        # EnhancedSecurityScanner has built-in engines, no need to add them manually
        
        logger.debug("ScannerCamper initialized")
    
    async def start(self) -> None:
        """Start the Scanner camper"""
        self._running = True
        
        # Initialize VALI coordinator if available
        try:
            self.vali_coordinator = VALICoordinator()
            await self.vali_coordinator.start()
            logger.debug("VALI coordinator started for scanner")
        except Exception as e:
            logger.warning(f"Could not start VALI coordinator: {e}")
        
        logger.info("ScannerCamper started")
    
    async def stop(self) -> None:
        """Stop the Scanner camper"""
        self._running = False
        
        if self.vali_coordinator:
            await self.vali_coordinator.stop()
        
        logger.info("ScannerCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Scan torch content for security threats.
        
        Args:
            torch: The torch to scan
            
        Returns:
            Dict containing scan results and recommendations
        """
        if not self._running:
            raise RuntimeError("ScannerCamper is not running")
        
        logger.debug(f"Scanning torch {torch.id}")
        
        try:
            # Perform security scan
            scan_result = await self.security_scanner.comprehensive_scan(torch, SecurityLevel.STANDARD)
            
            # Additional VALI validation if available
            vali_result = None
            if self.vali_coordinator:
                try:
                    vali_result = await self.vali_coordinator.validate_content(
                        torch.payload, 
                        VALIServiceType.CONTENT_VALIDATION
                    )
                except Exception as e:
                    logger.warning(f"VALI validation failed: {e}")
            
            # Determine action based on threat level
            action = self._determine_action(scan_result, vali_result)
            
            result = {
                'torch_id': torch.id,
                'scan_result': scan_result,
                'vali_result': vali_result,
                'action': action,
                'timestamp': datetime.utcnow().isoformat(),
                'scanner': 'ScannerCamper'
            }
            
            logger.debug(f"Scan completed for torch {torch.id}: {action}")
            return result
            
        except Exception as e:
            logger.error(f"Error scanning torch {torch.id}: {e}")
            return {
                'torch_id': torch.id,
                'error': str(e),
                'action': 'quarantine',  # Safe default
                'timestamp': datetime.utcnow().isoformat(),
                'scanner': 'ScannerCamper'
            }
    
    def _determine_action(self, scan_result: ScanResult, vali_result: Optional[Dict]) -> str:
        """Determine action based on scan results"""
        if scan_result.threat_level.value >= self.threat_threshold.value:
            return 'quarantine'
        elif scan_result.threat_level == ThreatLevel.MEDIUM:
            return 'sanitize'
        elif vali_result and not vali_result.get('is_valid', True):
            return 'sanitize'
        else:
            return 'allow'


class FilterCamper(ICamper):
    """
    Filter camper handles content sanitization and filtering.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Filter camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.sanitization_level = SanitizationLevel(config.get('sanitization_level', 'STANDARD'))
        self.custom_rules: List[SanitizationRule] = []
        self.preserve_formatting = config.get('preserve_formatting', True)
        self._running = False
        
        # Load default sanitization rules
        self._load_default_rules()
        
        logger.debug("FilterCamper initialized")
    
    async def start(self) -> None:
        """Start the Filter camper"""
        self._running = True
        logger.info("FilterCamper started")
    
    async def stop(self) -> None:
        """Stop the Filter camper"""
        self._running = False
        logger.info("FilterCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Sanitize torch content based on configured rules.
        
        Args:
            torch: The torch to sanitize
            
        Returns:
            Dict containing sanitized content and applied rules
        """
        if not self._running:
            raise RuntimeError("FilterCamper is not running")
        
        logger.debug(f"Sanitizing torch {torch.id}")
        
        try:
            # Create sanitized copy of payload
            sanitized_payload = await self._sanitize_payload(torch.payload)
            
            # Track applied rules
            applied_rules = self._get_applied_rules(torch.payload, sanitized_payload)
            
            result = {
                'torch_id': torch.id,
                'original_payload': torch.payload,
                'sanitized_payload': sanitized_payload,
                'applied_rules': applied_rules,
                'sanitization_level': self.sanitization_level.value,
                'timestamp': datetime.utcnow().isoformat(),
                'filter': 'FilterCamper'
            }
            
            logger.debug(f"Sanitization completed for torch {torch.id}")
            return result
            
        except Exception as e:
            logger.error(f"Error sanitizing torch {torch.id}: {e}")
            return {
                'torch_id': torch.id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'filter': 'FilterCamper'
            }
    
    async def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize payload content"""
        sanitized = {}
        
        for key, value in payload.items():
            if isinstance(value, str):
                sanitized[key] = await self._sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = await self._sanitize_payload(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    await self._sanitize_string(item) if isinstance(item, str)
                    else await self._sanitize_payload(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def _sanitize_string(self, text: str) -> str:
        """Apply sanitization rules to a string"""
        sanitized = text
        
        # Apply built-in sanitization based on level
        if self.sanitization_level in [SanitizationLevel.STANDARD, SanitizationLevel.STRICT, SanitizationLevel.AGGRESSIVE]:
            # HTML escape
            sanitized = html.escape(sanitized)
            
            # Remove script tags
            sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
            
            # Remove dangerous attributes
            sanitized = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', sanitized, flags=re.IGNORECASE)
        
        if self.sanitization_level in [SanitizationLevel.STRICT, SanitizationLevel.AGGRESSIVE]:
            # Remove all HTML tags
            sanitized = re.sub(r'<[^>]+>', '', sanitized)
            
            # Remove URLs in aggressive mode
            if self.sanitization_level == SanitizationLevel.AGGRESSIVE:
                sanitized = re.sub(r'https?://[^\s]+', '[URL_REMOVED]', sanitized)
        
        # Apply custom rules
        for rule in self.custom_rules:
            if rule.enabled:
                sanitized = re.sub(rule.pattern, rule.replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    def _load_default_rules(self) -> None:
        """Load default sanitization rules"""
        default_rules = [
            SanitizationRule(
                name="remove_javascript",
                pattern=r'javascript:[^"\']*',
                replacement='[SCRIPT_REMOVED]',
                severity=ThreatLevel.HIGH,
                description="Remove JavaScript URLs"
            ),
            SanitizationRule(
                name="remove_data_urls",
                pattern=r'data:[^"\']*',
                replacement='[DATA_URL_REMOVED]',
                severity=ThreatLevel.MEDIUM,
                description="Remove data URLs"
            ),
            SanitizationRule(
                name="sanitize_sql_injection",
                pattern=r'(union|select|insert|update|delete|drop|create|alter)\s+',
                replacement='[SQL_REMOVED]',
                severity=ThreatLevel.HIGH,
                description="Remove potential SQL injection"
            )
        ]
        
        self.custom_rules.extend(default_rules)
    
    def _get_applied_rules(self, original: Dict[str, Any], sanitized: Dict[str, Any]) -> List[str]:
        """Determine which rules were applied during sanitization"""
        applied = []
        
        # Simple comparison - in production, this would be more sophisticated
        if original != sanitized:
            applied.append(f"sanitization_level_{self.sanitization_level.value}")
        
        return applied
    
    def add_custom_rule(self, rule: SanitizationRule) -> None:
        """Add a custom sanitization rule"""
        self.custom_rules.append(rule)
        logger.info(f"Added custom sanitization rule: {rule.name}")


class QuarantineCamper(ICamper):
    """
    Quarantine camper manages quarantined content and review processes.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Quarantine camper.
        
        Args:
            config: Camper configuration from campfire steps
        """
        self.config = config
        self.quarantine_storage: Dict[str, QuarantineItem] = {}
        self.auto_review_enabled = config.get('auto_review_enabled', False)
        self.quarantine_ttl_days = config.get('quarantine_ttl_days', 30)
        self.max_quarantine_size = config.get('max_quarantine_size', 1000)
        self._running = False
        
        logger.debug("QuarantineCamper initialized")
    
    async def start(self) -> None:
        """Start the Quarantine camper"""
        self._running = True
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_task())
        
        logger.info("QuarantineCamper started")
    
    async def stop(self) -> None:
        """Stop the Quarantine camper"""
        self._running = False
        logger.info("QuarantineCamper stopped")
    
    async def process(self, torch: Torch) -> Dict[str, Any]:
        """
        Quarantine torch content.
        
        Args:
            torch: The torch to quarantine
            
        Returns:
            Dict containing quarantine information
        """
        if not self._running:
            raise RuntimeError("QuarantineCamper is not running")
        
        logger.debug(f"Quarantining torch {torch.id}")
        
        try:
            # Create quarantine item
            quarantine_id = self._generate_quarantine_id(torch)
            quarantine_item = QuarantineItem(
                id=quarantine_id,
                content=torch.payload,
                reason="Security scan flagged content",
                quarantined_at=datetime.utcnow(),
                torch_id=torch.id,
                sender_valley=torch.sender_valley
            )
            
            # Store in quarantine
            self.quarantine_storage[quarantine_id] = quarantine_item
            
            # Enforce size limits
            await self._enforce_size_limits()
            
            result = {
                'torch_id': torch.id,
                'quarantine_id': quarantine_id,
                'quarantined_at': quarantine_item.quarantined_at.isoformat(),
                'reason': quarantine_item.reason,
                'auto_review': self.auto_review_enabled,
                'timestamp': datetime.utcnow().isoformat(),
                'quarantine': 'QuarantineCamper'
            }
            
            logger.info(f"Torch {torch.id} quarantined as {quarantine_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error quarantining torch {torch.id}: {e}")
            return {
                'torch_id': torch.id,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'quarantine': 'QuarantineCamper'
            }
    
    async def review_item(self, quarantine_id: str, decision: str, reviewer: str) -> Dict[str, Any]:
        """Review a quarantined item"""
        if quarantine_id not in self.quarantine_storage:
            return {'error': 'Quarantine item not found'}
        
        item = self.quarantine_storage[quarantine_id]
        item.review_status = decision
        item.reviewer = reviewer
        item.reviewed_at = datetime.utcnow()
        
        logger.info(f"Quarantine item {quarantine_id} reviewed: {decision} by {reviewer}")
        
        return {
            'quarantine_id': quarantine_id,
            'decision': decision,
            'reviewer': reviewer,
            'reviewed_at': item.reviewed_at.isoformat()
        }
    
    async def get_quarantine_stats(self) -> Dict[str, Any]:
        """Get quarantine statistics"""
        total_items = len(self.quarantine_storage)
        pending_review = sum(1 for item in self.quarantine_storage.values() 
                           if item.review_status == 'pending')
        approved = sum(1 for item in self.quarantine_storage.values() 
                      if item.review_status == 'approved')
        rejected = sum(1 for item in self.quarantine_storage.values() 
                      if item.review_status == 'rejected')
        
        return {
            'total_items': total_items,
            'pending_review': pending_review,
            'approved': approved,
            'rejected': rejected,
            'storage_usage': f"{total_items}/{self.max_quarantine_size}"
        }
    
    def _generate_quarantine_id(self, torch: Torch) -> str:
        """Generate unique quarantine ID"""
        content_hash = hashlib.sha256(
            json.dumps(torch.payload, sort_keys=True).encode()
        ).hexdigest()[:16]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"quarantine_{timestamp}_{content_hash}"
    
    async def _enforce_size_limits(self) -> None:
        """Enforce quarantine size limits"""
        if len(self.quarantine_storage) > self.max_quarantine_size:
            # Remove oldest items
            sorted_items = sorted(
                self.quarantine_storage.items(),
                key=lambda x: x[1].quarantined_at
            )
            
            items_to_remove = len(self.quarantine_storage) - self.max_quarantine_size
            for i in range(items_to_remove):
                quarantine_id = sorted_items[i][0]
                del self.quarantine_storage[quarantine_id]
                logger.info(f"Removed old quarantine item {quarantine_id} due to size limits")
    
    async def _cleanup_task(self) -> None:
        """Background task to clean up old quarantine items"""
        while self._running:
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=self.quarantine_ttl_days)
                items_to_remove = [
                    qid for qid, item in self.quarantine_storage.items()
                    if item.quarantined_at < cutoff_date
                ]
                
                for qid in items_to_remove:
                    del self.quarantine_storage[qid]
                    logger.debug(f"Cleaned up expired quarantine item {qid}")
                
                if items_to_remove:
                    logger.info(f"Cleaned up {len(items_to_remove)} expired quarantine items")
                
            except Exception as e:
                logger.error(f"Error in quarantine cleanup task: {e}")
            
            # Sleep for 1 hour
            await asyncio.sleep(3600)


class SanitizerCampfire(Campfire, ISanitizerCampfire):
    """
    Sanitizer campfire that orchestrates content scanning, filtering, and quarantine.
    
    This campfire provides comprehensive content security functionality,
    protecting valleys from malicious or inappropriate content.
    """
    
    def __init__(self, mcp_broker: IMCPBroker, config: Optional[CampfireConfig] = None):
        """
        Initialize the Sanitizer campfire.
        
        Args:
            mcp_broker: MCP broker for communication
            config: Optional campfire configuration (will create default if not provided)
        """
        if config is None:
            config = self._create_default_config()
        
        super().__init__(config, mcp_broker)
        
        # Initialize campers
        self.scanner = ScannerCamper(self._get_camper_config('scanner'))
        self.filter = FilterCamper(self._get_camper_config('filter'))
        self.quarantine = QuarantineCamper(self._get_camper_config('quarantine'))
        
        self._campers = {
            'scanner': self.scanner,
            'filter': self.filter,
            'quarantine': self.quarantine
        }
        
        logger.info("SanitizerCampfire initialized")
    
    async def start(self) -> None:
        """Start the Sanitizer campfire and all campers"""
        await super().start()
        
        # Start all campers
        for camper_name, camper in self._campers.items():
            await camper.start()
            logger.debug(f"Started {camper_name} camper")
        
        logger.info("SanitizerCampfire started with all campers")
    
    async def stop(self) -> None:
        """Stop the Sanitizer campfire and all campers"""
        # Stop all campers
        for camper_name, camper in self._campers.items():
            await camper.stop()
            logger.debug(f"Stopped {camper_name} camper")
        
        await super().stop()
        logger.info("SanitizerCampfire stopped")
    
    async def process_torch(self, torch: Torch) -> Optional[Torch]:
        """
        Process torch through sanitization pipeline.
        
        Args:
            torch: The torch to process
            
        Returns:
            Processed torch or None if quarantined
        """
        logger.info(f"Processing torch {torch.id} through sanitization pipeline")
        
        try:
            # Step 1: Scan content
            scan_result = await self.scanner.process(torch)
            action = scan_result.get('action', 'allow')
            
            if action == 'quarantine':
                # Quarantine the torch
                await self.quarantine.process(torch)
                logger.warning(f"Torch {torch.id} quarantined due to security scan")
                return None
            
            elif action == 'sanitize':
                # Sanitize the content
                filter_result = await self.filter.process(torch)
                
                if 'sanitized_payload' in filter_result:
                    # Create sanitized torch
                    sanitized_torch = Torch(
                        id=torch.id,
                        sender_valley=torch.sender_valley,
                        target_address=torch.target_address,
                        payload=filter_result['sanitized_payload'],
                        attachments=torch.attachments.copy(),
                        signature=torch.signature,
                        timestamp=torch.timestamp
                    )
                    
                    logger.info(f"Torch {torch.id} sanitized and processed")
                    return sanitized_torch
                else:
                    logger.error(f"Failed to sanitize torch {torch.id}")
                    return None
            
            else:  # action == 'allow'
                logger.info(f"Torch {torch.id} passed security scan")
                return torch
        
        except Exception as e:
            logger.error(f"Error processing torch {torch.id}: {e}")
            # Safe default: quarantine on error
            await self.quarantine.process(torch)
            return None
    
    # ISanitizerCampfire interface implementation
    async def scan_content(self, content: Dict[str, Any]) -> ScanResult:
        """Content security scanning"""
        # Create temporary torch for scanning
        temp_torch = Torch(
            id="temp_scan",
            sender_valley="system",
            target_address="scanner",
            payload=content,
            attachments=[],
            signature="",
            timestamp=datetime.utcnow()
        )
        
        scan_result = await self.scanner.process(temp_torch)
        
        # Convert to ScanResult format
        return ScanResult(
            is_safe=scan_result.get('action') == 'allow',
            threat_level=ThreatLevel.LOW,  # Default, would be determined by actual scan
            threats_found=[],
            scan_duration=0.0,
            scanner_version="1.0"
        )
    
    async def filter_unsafe_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Filter and remove unsafe content"""
        temp_torch = Torch(
            id="temp_filter",
            sender_valley="system",
            target_address="filter",
            payload=content,
            attachments=[],
            signature="",
            timestamp=datetime.utcnow()
        )
        
        filter_result = await self.filter.process(temp_torch)
        return filter_result.get('sanitized_payload', content)
    
    async def quarantine_flagged_content(self, content: Dict[str, Any]) -> None:
        """Move flagged content to quarantine"""
        temp_torch = Torch(
            id="temp_quarantine",
            sender_valley="system",
            target_address="quarantine",
            payload=content,
            attachments=[],
            signature="",
            timestamp=datetime.utcnow()
        )
        
        await self.quarantine.process(temp_torch)
    
    def _create_default_config(self) -> CampfireConfig:
        """Create default configuration for Sanitizer campfire"""
        return CampfireConfig(
            name="sanitizer",
            runs_on="valley",
            env={
                "SANITIZER_MODE": "standard",
                "THREAT_THRESHOLD": "MEDIUM"
            },
            steps=[
                {
                    "name": "Scan content for threats",
                    "uses": "camper/scanner@v1",
                    "with": {
                        "scan_engines": ["MALWARE_DETECTOR", "XSS_DETECTOR", "CONTENT_POLICY"],
                        "threat_threshold": "MEDIUM"
                    }
                },
                {
                    "name": "Filter unsafe content",
                    "uses": "camper/filter@v1",
                    "with": {
                        "sanitization_level": "STANDARD",
                        "preserve_formatting": True
                    }
                },
                {
                    "name": "Manage quarantined content",
                    "uses": "camper/quarantine@v1",
                    "with": {
                        "auto_review_enabled": False,
                        "quarantine_ttl_days": 30,
                        "max_quarantine_size": 1000
                    }
                }
            ],
            channels=["content-security", "sanitizer-control"],
            auditor_enabled=True
        )
    
    def _get_camper_config(self, camper_name: str) -> Dict[str, Any]:
        """Extract configuration for a specific camper from campfire steps"""
        for step in self.config.steps:
            uses = step.get('uses', '')
            if f'camper/{camper_name}@' in uses:
                return step.get('with', {})
        
        # Return default config if not found
        defaults = {
            'scanner': {
                'scan_engines': ['MALWARE_DETECTOR', 'XSS_DETECTOR'],
                'threat_threshold': 'MEDIUM'
            },
            'filter': {
                'sanitization_level': 'STANDARD',
                'preserve_formatting': True
            },
            'quarantine': {
                'auto_review_enabled': False,
                'quarantine_ttl_days': 30,
                'max_quarantine_size': 1000
            }
        }
        
        return defaults.get(camper_name, {})
    
    def get_campers(self) -> Dict[str, ICamper]:
        """Get all active campers"""
        return self._campers.copy()
    
    async def get_quarantine_stats(self) -> Dict[str, Any]:
        """Get quarantine statistics"""
        return await self.quarantine.get_quarantine_stats()
    
    async def review_quarantine_item(self, quarantine_id: str, decision: str, reviewer: str) -> Dict[str, Any]:
        """Review a quarantined item"""
        return await self.quarantine.review_item(quarantine_id, decision, reviewer)
    
    def __repr__(self) -> str:
        return f"SanitizerCampfire(running={self._running}, campers={len(self._campers)})"