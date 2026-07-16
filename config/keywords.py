"""
Search keyword list for aggregator queries — PRD §6.2 taxonomy.
These are the terms sent to Tender Tiger / Tender247 / GeM search.
Generic single words from the taxonomy (server, battery, monitor, tablet...)
are deliberately excluded here: they flood search results. They remain
classification signals inside the LLM skill, which sees full tender text.
"""

SEARCH_KEYWORDS = [
    # Video surveillance
    "cctv", "surveillance", "ip camera", "nvr", "vms", "anpr", "ptz camera",
    # Intrusion
    "security alarm", "burglar alarm", "intrusion detection",
    # Public address & audio
    "public address", "pa system", "conference system",
    # Access control & biometrics
    "biometric", "access control", "rfid",
    # Security screening
    "hhmd", "dfmd", "baggage scanner", "xbis",
    # Building management
    "building management system", "bms",
    # Fire detection & alarm
    "fire alarm", "fire detection", "smoke detector", "addressable fire alarm",
    "gas detection", "evac",
    # Fire suppression & safety
    "fire suppression", "clean agent", "novec", "fk-5", "fire extinguisher",
    "fire fighting", "fire protection", "fire door", "fire hydrant",
    # Communication & specialized
    "video door phone", "nurse call", "turnstile", "boom barrier", "bollard",
    "visitor management",
    # Supporting infrastructure
    "water leak detection", "guard tour", "smart rack",
    # Security & facility services
    "security manpower", "security guard", "facility management",
    "housekeeping", "cash in transit",
    # Contract types
    "cctv amc", "fire alarm amc", "sitc",
]
