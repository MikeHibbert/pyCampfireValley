"""
Enhanced Security Scanner for CampfireValley

This module provides comprehensive security scanning capabilities for torches,
including payload analysis, attachment scanning, signature verification,
and threat detection using multiple scanning engines.
"""

import asyncio
import hashlib
import re
import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

from .models import Torch, ScanResult, Violation, SecurityLevel
from .vali import BaseVALIService, VALIServiceType, VALIServiceStatus, VALIServiceResponse


class ThreatLevel(str, Enum):
    """Threat severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScanEngine(str, Enum):
    """Available scanning engines"""
    PATTERN_MATCHER = "pattern_matcher"
    HEURISTIC_ANALYZER = "heuristic_analyzer"
    SIGNATURE_VALIDATOR = "signature_validator"
    CONTENT_INSPECTOR = "content_inspector"
    BEHAVIORAL_ANALYZER = "behavioral_analyzer"


@dataclass
class ThreatSignature:
    """Represents a threat signature for detection"""
    name: str
    pattern: str
    threat_level: ThreatLevel
    description: str
    category: str
    regex_flags: int = re.IGNORECASE


@dataclass
class ScanEngineResult:
    """Result from a single scanning engine"""
    engine: ScanEngine
    threats_found: List[str]
    confidence: float
    scan_time_ms: int
    metadata: Dict[str, Any]


class ThreatDatabase:
    """Database of known threat signatures and patterns"""
    
    def __init__(self):
        self.signatures: List[ThreatSignature] = []
        self._load_default_signatures()
    
    def _load_default_signatures(self):
        """Load default threat signatures"""
        default_signatures = [
            # XSS Patterns
            ThreatSignature(
                name="XSS_SCRIPT_TAG",
                pattern=r"<script[^>]*>.*?</script>",
                threat_level=ThreatLevel.HIGH,
                description="Cross-site scripting via script tags",
                category="xss"
            ),
            ThreatSignature(
                name="XSS_EVENT_HANDLER",
                pattern=r"on\w+\s*=\s*[\"'][^\"']*[\"']",
                threat_level=ThreatLevel.MEDIUM,
                description="XSS via event handlers",
                category="xss"
            ),
            
            # SQL Injection
            ThreatSignature(
                name="SQL_INJECTION_UNION",
                pattern=r"\bunion\s+select\b",
                threat_level=ThreatLevel.HIGH,
                description="SQL injection using UNION SELECT",
                category="sql_injection"
            ),
            ThreatSignature(
                name="SQL_INJECTION_COMMENT",
                pattern=r"(--|#|/\*|\*/)",
                threat_level=ThreatLevel.MEDIUM,
                description="SQL comment injection",
                category="sql_injection"
            ),
            
            # Code Execution
            ThreatSignature(
                name="CODE_EXEC_EVAL",
                pattern=r"\b(eval|exec|system|shell_exec|passthru)\s*\(",
                threat_level=ThreatLevel.CRITICAL,
                description="Code execution functions",
                category="code_execution"
            ),
            
            # Path Traversal
            ThreatSignature(
                name="PATH_TRAVERSAL",
                pattern=r"\.\.[\\/]",
                threat_level=ThreatLevel.HIGH,
                description="Directory traversal attempt",
                category="path_traversal"
            ),
            
            # Command Injection
            ThreatSignature(
                name="COMMAND_INJECTION",
                pattern=r"[;&|`$(){}[\]<>]",
                threat_level=ThreatLevel.MEDIUM,
                description="Command injection characters",
                category="command_injection"
            ),
            
            # Suspicious URLs
            ThreatSignature(
                name="SUSPICIOUS_URL",
                pattern=r"https?://[^\s]*\.(tk|ml|ga|cf|bit\.ly|tinyurl)",
                threat_level=ThreatLevel.MEDIUM,
                description="Suspicious URL domains",
                category="suspicious_url"
            ),
            
            # Data Exfiltration
            ThreatSignature(
                name="BASE64_ENCODED",
                pattern=r"[A-Za-z0-9+/]{20,}={0,2}",
                threat_level=ThreatLevel.LOW,
                description="Potential base64 encoded data",
                category="data_exfiltration"
            ),
        ]
        
        self.signatures.extend(default_signatures)
    
    def add_signature(self, signature: ThreatSignature):
        """Add a custom threat signature"""
        self.signatures.append(signature)
    
    def get_signatures_by_category(self, category: str) -> List[ThreatSignature]:
        """Get signatures by category"""
        return [sig for sig in self.signatures if sig.category == category]
    
    def get_signatures_by_threat_level(self, min_level: ThreatLevel) -> List[ThreatSignature]:
        """Get signatures by minimum threat level"""
        level_order = {
            ThreatLevel.LOW: 0,
            ThreatLevel.MEDIUM: 1,
            ThreatLevel.HIGH: 2,
            ThreatLevel.CRITICAL: 3
        }
        min_order = level_order[min_level]
        return [sig for sig in self.signatures if level_order[sig.threat_level] >= min_order]


class PatternMatchingEngine:
    """Pattern-based threat detection engine"""
    
    def __init__(self, threat_db: ThreatDatabase):
        self.threat_db = threat_db
        self.logger = logging.getLogger(f"{__name__}.PatternMatchingEngine")
    
    async def scan(self, content: str, security_level: SecurityLevel) -> ScanEngineResult:
        """Scan content using pattern matching"""
        start_time = datetime.utcnow()
        threats_found = []
        
        # Select signatures based on security level
        if security_level == SecurityLevel.HIGH:
            signatures = self.threat_db.signatures
        elif security_level == SecurityLevel.STANDARD:
            signatures = self.threat_db.get_signatures_by_threat_level(ThreatLevel.MEDIUM)
        else:  # BASIC
            signatures = self.threat_db.get_signatures_by_threat_level(ThreatLevel.HIGH)
        
        # Scan content against signatures
        for signature in signatures:
            try:
                if re.search(signature.pattern, content, signature.regex_flags):
                    threats_found.append(f"{signature.name}: {signature.description}")
            except re.error as e:
                self.logger.warning(f"Invalid regex pattern {signature.name}: {e}")
        
        scan_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        confidence = 0.9 if threats_found else 1.0
        
        return ScanEngineResult(
            engine=ScanEngine.PATTERN_MATCHER,
            threats_found=threats_found,
            confidence=confidence,
            scan_time_ms=scan_time,
            metadata={
                "signatures_checked": len(signatures),
                "content_length": len(content)
            }
        )


class HeuristicAnalyzer:
    """Heuristic-based threat analysis engine"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.HeuristicAnalyzer")
    
    async def scan(self, torch: Torch) -> ScanEngineResult:
        """Perform heuristic analysis on torch"""
        start_time = datetime.utcnow()
        threats_found = []
        
        # Analyze payload structure
        payload_str = json.dumps(torch.payload)
        
        # Check for suspicious characteristics
        if len(payload_str) > 100000:  # 100KB
            threats_found.append("Unusually large payload size")
        
        if torch.payload.get("type") == "executable":
            threats_found.append("Executable content detected")
        
        # Check for nested depth (potential zip bomb)
        max_depth = self._calculate_nesting_depth(torch.payload)
        if max_depth > 10:
            threats_found.append(f"Excessive nesting depth: {max_depth}")
        
        # Check for suspicious field names
        suspicious_fields = ["password", "secret", "key", "token", "auth"]
        for field in suspicious_fields:
            if any(field in str(k).lower() for k in self._get_all_keys(torch.payload)):
                threats_found.append(f"Suspicious field name detected: {field}")
        
        # Check attachment count
        if len(torch.attachments) > 50:
            threats_found.append(f"Excessive attachment count: {len(torch.attachments)}")
        
        # Check for time anomalies
        if torch.timestamp > datetime.utcnow() + timedelta(hours=1):
            threats_found.append("Future timestamp detected")
        
        scan_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        confidence = 0.8 if threats_found else 0.95
        
        return ScanEngineResult(
            engine=ScanEngine.HEURISTIC_ANALYZER,
            threats_found=threats_found,
            confidence=confidence,
            scan_time_ms=scan_time,
            metadata={
                "payload_size": len(payload_str),
                "attachment_count": len(torch.attachments),
                "nesting_depth": max_depth
            }
        )
    
    def _calculate_nesting_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Calculate maximum nesting depth of an object"""
        if current_depth > 20:  # Prevent infinite recursion
            return current_depth
        
        if isinstance(obj, dict):
            if not obj:
                return current_depth
            return max(self._calculate_nesting_depth(v, current_depth + 1) for v in obj.values())
        elif isinstance(obj, list):
            if not obj:
                return current_depth
            return max(self._calculate_nesting_depth(item, current_depth + 1) for item in obj)
        else:
            return current_depth
    
    def _get_all_keys(self, obj: Any) -> Set[str]:
        """Get all keys from nested dictionary structure"""
        keys = set()
        if isinstance(obj, dict):
            keys.update(obj.keys())
            for value in obj.values():
                keys.update(self._get_all_keys(value))
        elif isinstance(obj, list):
            for item in obj:
                keys.update(self._get_all_keys(item))
        return keys


class ContentInspector:
    """Content structure and format inspector"""
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.ContentInspector")
    
    async def scan(self, torch: Torch) -> ScanEngineResult:
        """Inspect torch content structure"""
        start_time = datetime.utcnow()
        threats_found = []
        
        # Check payload structure
        if not isinstance(torch.payload, dict):
            threats_found.append("Invalid payload structure - must be dictionary")
        
        # Check for required fields
        required_fields = ["type"]
        for field in required_fields:
            if field not in torch.payload:
                threats_found.append(f"Missing required field: {field}")
        
        # Check for circular references
        try:
            json.dumps(torch.payload)
        except (TypeError, ValueError) as e:
            threats_found.append(f"Payload serialization error: {e}")
        
        # Validate attachments
        for i, attachment in enumerate(torch.attachments):
            if not isinstance(attachment, str):
                threats_found.append(f"Invalid attachment format at index {i}")
            elif len(attachment) > 1000:
                threats_found.append(f"Attachment reference too long at index {i}")
        
        # Check signature format
        if not torch.signature or len(torch.signature) < 32:
            threats_found.append("Invalid or missing signature")
        
        scan_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        confidence = 0.95 if not threats_found else 0.7
        
        return ScanEngineResult(
            engine=ScanEngine.CONTENT_INSPECTOR,
            threats_found=threats_found,
            confidence=confidence,
            scan_time_ms=scan_time,
            metadata={
                "payload_type": type(torch.payload).__name__,
                "attachment_count": len(torch.attachments)
            }
        )


class EnhancedSecurityScanner(BaseVALIService):
    """
    Enhanced security scanner with multiple scanning engines
    """
    
    def __init__(self):
        super().__init__(
            VALIServiceType.SECURITY_SCAN,
            {
                "engines": [engine.value for engine in ScanEngine],
                "threat_levels": [level.value for level in ThreatLevel],
                "security_levels": [level.value for level in SecurityLevel],
                "max_payload_size": 10 * 1024 * 1024,  # 10MB
                "max_attachments": 100
            }
        )
        
        self.threat_db = ThreatDatabase()
        self.pattern_engine = PatternMatchingEngine(self.threat_db)
        self.heuristic_engine = HeuristicAnalyzer()
        self.content_inspector = ContentInspector()
        
        self._scan_cache: Dict[str, Tuple[ScanResult, datetime]] = {}
        self._cache_ttl = timedelta(minutes=30)
    
    async def process_request(self, request) -> VALIServiceResponse:
        """Process security scan request"""
        try:
            # Extract torch data from request
            torch_data = request.payload
            torch = Torch(
                id=torch_data.get("torch_id", "unknown"),
                sender_valley=torch_data.get("sender_valley", "unknown"),
                target_address=torch_data.get("target_address", "unknown"),
                payload=torch_data.get("payload", {}),
                attachments=torch_data.get("attachments", []),
                signature=torch_data.get("signature", ""),
                timestamp=datetime.utcnow()
            )
            
            security_level = SecurityLevel(
                request.requirements.get("security_level", SecurityLevel.STANDARD.value)
            )
            
            # Check cache first
            cache_key = self._generate_cache_key(torch)
            cached_result = self._get_cached_result(cache_key)
            if cached_result:
                return VALIServiceResponse(
                    request_id=request.request_id,
                    status=VALIServiceStatus.COMPLETED.value,
                    deliverables={"scan_result": cached_result.dict()},
                    metadata={"cached": True}
                )
            
            # Perform comprehensive scan
            scan_result = await self.comprehensive_scan(torch, security_level)
            
            # Cache result
            self._cache_result(cache_key, scan_result)
            
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.COMPLETED.value,
                deliverables={"scan_result": scan_result.dict()},
                metadata={"cached": False}
            )
            
        except Exception as e:
            self.logger.error(f"Security scan failed: {e}")
            return VALIServiceResponse(
                request_id=request.request_id,
                status=VALIServiceStatus.FAILED.value,
                deliverables={},
                metadata={"error": str(e)}
            )
    
    async def comprehensive_scan(self, torch: Torch, security_level: SecurityLevel) -> ScanResult:
        """Perform comprehensive security scan"""
        start_time = datetime.utcnow()
        
        # Run all scanning engines concurrently
        content = json.dumps(torch.payload)
        
        scan_tasks = [
            self.pattern_engine.scan(content, security_level),
            self.heuristic_engine.scan(torch),
            self.content_inspector.scan(torch)
        ]
        
        engine_results = await asyncio.gather(*scan_tasks, return_exceptions=True)
        
        # Aggregate results
        all_violations = []
        total_confidence = 0.0
        valid_results = 0
        
        for result in engine_results:
            if isinstance(result, ScanEngineResult):
                all_violations.extend(result.threats_found)
                total_confidence += result.confidence
                valid_results += 1
            else:
                self.logger.warning(f"Scan engine failed: {result}")
        
        # Calculate overall confidence
        overall_confidence = total_confidence / valid_results if valid_results > 0 else 0.0
        
        # Determine if torch is safe
        is_safe = len(all_violations) == 0
        
        # Adjust confidence based on violations
        if all_violations:
            overall_confidence *= 0.5  # Reduce confidence when violations found
        
        scan_duration = datetime.utcnow() - start_time
        
        return ScanResult(
            is_safe=is_safe,
            violations=all_violations,
            confidence_score=min(overall_confidence, 1.0),
            scan_timestamp=datetime.utcnow()
        )
    
    def _generate_cache_key(self, torch: Torch) -> str:
        """Generate cache key for torch"""
        content = f"{torch.id}:{torch.sender_valley}:{json.dumps(torch.payload, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_cached_result(self, cache_key: str) -> Optional[ScanResult]:
        """Get cached scan result if still valid"""
        if cache_key in self._scan_cache:
            result, timestamp = self._scan_cache[cache_key]
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return result
            else:
                del self._scan_cache[cache_key]
        return None
    
    def _cache_result(self, cache_key: str, result: ScanResult):
        """Cache scan result"""
        self._scan_cache[cache_key] = (result, datetime.utcnow())
        
        # Clean old cache entries
        current_time = datetime.utcnow()
        expired_keys = [
            key for key, (_, timestamp) in self._scan_cache.items()
            if current_time - timestamp > self._cache_ttl
        ]
        for key in expired_keys:
            del self._scan_cache[key]
    
    def add_custom_signature(self, signature: ThreatSignature):
        """Add custom threat signature"""
        self.threat_db.add_signature(signature)
        self.logger.info(f"Added custom threat signature: {signature.name}")
    
    def get_threat_statistics(self) -> Dict[str, Any]:
        """Get threat detection statistics"""
        return {
            "total_signatures": len(self.threat_db.signatures),
            "signatures_by_category": {
                category: len(self.threat_db.get_signatures_by_category(category))
                for category in set(sig.category for sig in self.threat_db.signatures)
            },
            "cache_size": len(self._scan_cache),
            "cache_hit_rate": getattr(self, '_cache_hits', 0) / max(getattr(self, '_cache_requests', 1), 1)
        }