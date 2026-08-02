# Enterprise Asset Management

Epic 7 adds a property-aware enterprise registry linked to legacy devices and CMDB CIs. Assets progress through Planned → Requested → Approved → Purchased → Received → Installed → Assigned → Operational → Maintenance → Loaned → Transferred → Retired → Disposed → Archived. Every transition records actor, reason, prior stage, current stage, and timestamp. Disposal requires a reviewed disposal record.

Financial fields use fixed-precision values. Straight-line and declining-balance depreciation derive from stored purchase cost, residual value, purchase date, and useful life. TCO adds recorded maintenance, repair, and replacement costs. Scheduled recalculation never recommends or initiates procurement.
