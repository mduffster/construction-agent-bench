"""Stable string enums used by ConstructBench schemas."""

from enum import StrEnum


class AgentRole(StrEnum):
    OWNER_DEVELOPER = "owner_developer"
    GENERAL_CONTRACTOR = "general_contractor"
    STEEL_SUPPLIER = "steel_supplier"
    LABOR_SUBCONTRACTOR = "labor_subcontractor"
    LENDER = "lender"
    INSPECTOR = "inspector"


class CommunicationVisibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class ContractStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    AMENDED = "amended"
    COMPLETE = "complete"
    BREACHED = "breached"
    CANCELLED = "cancelled"


class BreachProfile(StrEnum):
    EASY = "easy"
    HARD = "hard"


class BreachSeverity(StrEnum):
    MINOR = "minor"
    MATERIAL = "material"
    SEVERE = "severe"


class DecisionType(StrEnum):
    NONE = "none"
    REQUEST_INFORMATION = "request_information"
    SUBMIT_FORECAST = "submit_forecast"
    SUBMIT_REQUEST = "submit_request"
    APPROVE = "approve"
    REJECT = "reject"
    SCHEDULE = "schedule"
    PAY = "pay"
    INSPECT = "inspect"
    DECLARE_STATUS = "declare_status"


class InspectionStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    REQUESTED = "requested"
    SCHEDULED = "scheduled"
    PASSED = "passed"
    FAILED = "failed"
    REQUIRES_REWORK = "requires_rework"
    CANCELLED = "cancelled"


class LedgerEntryType(StrEnum):
    MARKET_UPDATE = "market_update"
    PROJECT_FORECAST = "project_forecast"
    PAYMENT_CONFIRMATION = "payment_confirmation"
    DRAW_APPROVAL = "draw_approval"
    DRAW_REJECTION = "draw_rejection"
    INSPECTION_OUTCOME = "inspection_outcome"
    CONTRACT_AMENDMENT = "contract_amendment"
    MILESTONE_STATUS = "milestone_status"
    PUBLIC_FORECAST = "public_forecast"
    AUDIT_FINDING = "audit_finding"
    AGENT_CLAIM = "agent_claim"
    ATTESTATION = "attestation"


class DisclosureAssessmentType(StrEnum):
    ACCURATE = "accurate"
    LATE = "late"
    OMITTED = "omitted"
    INACCURATE = "inaccurate"


class AssessmentUpdateMode(StrEnum):
    SCALAR_BASELINE = "scalar_baseline"
    STRUCTURED_DIMENSIONAL = "structured_dimensional"


class UnchangedReason(StrEnum):
    IRRELEVANT = "irrelevant"
    NONDIAGNOSTIC = "nondiagnostic"
    ALREADY_INCORPORATED = "already_incorporated"
    OFFSET_BY_REMEDIATION = "offset_by_remediation"
    ATTRIBUTION_UNCLEAR = "attribution_unclear"


class ObligationStatus(StrEnum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    BREACHED = "breached"


class ObligationType(StrEnum):
    DELIVERY = "delivery"
    COMPLETION_REPORT = "completion_report"
    FUNDING_DISCLOSURE = "funding_disclosure"
    CREW_AVAILABILITY = "crew_availability"
    DRAW_REVIEW = "draw_review"
    INSPECTION_STATUS = "inspection_status"
    ATTESTATION = "attestation"


class OversightFindingType(StrEnum):
    CONFLICTING_CLAIM = "conflicting_claim"
    MISSING_REPORT = "missing_report"
    OVERDUE_RESPONSE = "overdue_response"
    UNSUPPORTED_FORECAST = "unsupported_forecast"
    MISSED_ATTESTATION = "missed_attestation"
    INACCURATE_ATTESTATION = "inaccurate_attestation"
    BREACH_FLAG = "breach_flag"


class PrivateEventType(StrEnum):
    SUPPLIER_IMPACT_ASSESSMENT = "supplier_impact_assessment"
    ROLE_IMPACT_ASSESSMENT = "role_impact_assessment"
    PRIVATE_MESSAGE = "private_message"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"
    LATE = "late"
    CANCELLED = "cancelled"


class PolicyProfile(StrEnum):
    PROFIT_FIRST = "profit_first"
    BALANCED_COMMERCIAL = "balanced_commercial"
    INSTITUTIONAL = "institutional"


class ResourceConditionLevel(StrEnum):
    COMFORTABLE = "comfortable"
    NORMAL = "normal"
    STRAINED = "strained"


class BehaviorProfile(StrEnum):
    COLLABORATIVE = "collaborative"
    SELFISH = "selfish"
    PASSIVE = "passive"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    NOT_STARTED = "not_started"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    FAILED = "failed"
    REQUIRES_REWORK = "requires_rework"
    CANCELLED = "cancelled"


class ScheduledEventType(StrEnum):
    PUBLIC_LEDGER_ENTRY = "public_ledger_entry"
    PRIVATE_STATE_UPDATE = "private_state_update"
    PRIVATE_MESSAGE = "private_message"
