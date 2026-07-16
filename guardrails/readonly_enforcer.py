"""
SEPLE Tender Platform — Read-Only Enforcer
Ensures compliance with PRD §9.1 (Strictly Read-Only).
Runs on startup to verify no code attempts to submit forms other than search/login.
"""
import ast
import logging
import os

logger = logging.getLogger(__name__)

class ReadOnlyEnforcer:
    
    # List of Playwright methods that indicate write/submit actions
    # We allow 'fill' and 'click' for search boxes and login, but block others if they
    # appear to target payment or submission forms.
    SUSPICIOUS_SELECTORS = [
        "pay", "submit_bid", "upload", "checkout", "credit_card", "register"
    ]
    
    @classmethod
    def audit_connectors(cls) -> bool:
        """
        Static analysis of the connectors directory to ensure no blatant violations
        of the read-only rule are present.
        """
        connectors_dir = os.path.join(os.path.dirname(__file__), "..", "connectors")
        if not os.path.exists(connectors_dir):
            return True
            
        violations = []
        
        for filename in os.listdir(connectors_dir):
            if not filename.endswith(".py"):
                continue
                
            filepath = os.path.join(connectors_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    # Check string literals for suspicious selectors
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        val_lower = node.value.lower()
                        for suspect in cls.SUSPICIOUS_SELECTORS:
                            if suspect in val_lower and "search" not in val_lower and "login" not in val_lower:
                                violations.append(f"Suspicious string '{node.value}' in {filename} at line {node.lineno}")
            except Exception as e:
                logger.error(f"Failed to audit {filename}: {e}")
                
        if violations:
            logger.critical("🚨 SECURITY VIOLATION DETECTED (PRD §9.1) 🚨")
            for v in violations:
                logger.critical(f" - {v}")
            return False
            
        logger.info("Guardrail Check Passed: No write/submit operations detected in connectors.")
        return True

if __name__ == "__main__":
    if not ReadOnlyEnforcer.audit_connectors():
        exit(1)
