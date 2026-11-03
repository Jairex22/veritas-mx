"""EntitySets that GPV listed as available on the FactoryLogix OData service, grouped by area.

These are only *names of resources* reported by GPV. Whether each one exists, which properties it
has and whether this account may read it is determined ONLY by the real $metadata and by
controlled GET probes. Property names are never derived from these names.
"""
EXPECTED = {
    "Producción": ["ActiveProductTracking", "ActiveProductTrackingDetail", "WIP", "BatchSummary", "BatchStatus", "ProductionScheduling",
                   "ProductivityOverTime", "Yield", "OEE", "Utilization", "ProcessFlow", "Factory"],
    "Calidad": ["Quality", "QualityHistory", "Faults", "Symptoms", "SPCMeasurements", "SPCDefectiveUnits", "SPCTotalDefects", "DPMOInProcess",
                "DPMO7912", "ValidationExceptions", "NonConformanceActionPlans", "NonConformanceAffectedUnits", "NonConformanceApprovalDetails",
                "NonConformanceChangeHistory"],
    "SMT y equipos": ["SMT", "Printer", "ReflowOven", "WaveSolder", "Dispenser", "AlarmOccurences", "TestAndMeasurement", "ToolUsageHistory"],
    "Materiales": ["Inventory", "KittedMaterials", "MaterialReservations", "MaterialPurchaseOrders", "ReceivingQuality", "ReceivingQualityHistory",
                   "ReceivingYield", "GRNStatus"],
    "Trazabilidad": ["AssemblyGenealogy", "InstalledComponentRecord", "WhereFound", "PartRelationships", "TrackingNumbers", "BarcodeTemplate",
                     "Packout", "ShippingOrders", "TransportOrders"],
    "Ingeniería": ["CadBom", "ChangeNotices", "ProcessIntroductionReleases", "ProcessApprovals", "DocumentHistory"],
    "Administración": ["UserDetail", "UserCertification", "OperatorFeedback", "AuditLog", "AuditPlanning", "ArchiveAndRestoreHistory"],
}
CATEGORY_OF = {name: cat for cat, names in EXPECTED.items() for name in names}
# Entity sets whose content is personal / administrative: probes record only status and property NAMES.
SENSITIVE = {"UserDetail", "UserCertification", "OperatorFeedback", "AuditLog", "AuditPlanning", "ArchiveAndRestoreHistory"}


def category(name):
    return CATEGORY_OF.get(name, "Otras (solo en $metadata)")
