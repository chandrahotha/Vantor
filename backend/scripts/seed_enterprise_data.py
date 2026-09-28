"""Seed realistic enterprise procurement data: Indian and US suppliers, master contracts, notifications."""
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

# Ensure path is backend root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.tenant import get_engine, get_session_factory
from app.models.base import Base
from app.models.supplier import Supplier
from app.models.contract import Contract
from app.models.notification import Notification

def seed():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    factory = get_session_factory()
    db = factory()
    tenant = "vantor-corp"
    user_sub = "director"
    now = datetime.now(timezone.utc)

    try:
        # Check if already seeded
        existing_count = db.query(Supplier).filter(Supplier.tenant_id == tenant).count()
        if existing_count > 0:
            print(f"Database already has {existing_count} suppliers. Clearing to re-seed with rich enterprise data...")
            db.query(Notification).filter(Notification.tenant_id == tenant).delete()
            db.query(Contract).filter(Contract.tenant_id == tenant).delete()
            db.query(Supplier).filter(Supplier.tenant_id == tenant).delete()
            db.commit()

        suppliers_data = [
            {
                "code": "SUP-TCS-01",
                "name": "Tata Consultancy Services (TCS)",
                "status": "active",
                "country": "IN",
                "currency": "INR",
                "risk_tier": "low",
                "payment_terms": "Net 45",
                "notes": "Global strategic IT solutions and offshore engineering partner.",
            },
            {
                "code": "SUP-INFY-02",
                "name": "Infosys Technologies Ltd",
                "status": "active",
                "country": "IN",
                "currency": "INR",
                "risk_tier": "low",
                "payment_terms": "Net 30",
                "notes": "Core ERP migration, QA automation, and cloud delivery.",
            },
            {
                "code": "SUP-AWS-03",
                "name": "Amazon Web Services Enterprise",
                "status": "active",
                "country": "US",
                "currency": "USD",
                "risk_tier": "low",
                "payment_terms": "Net 30",
                "notes": "Primary cloud compute, storage, VPC interconnect, and AI services.",
            },
            {
                "code": "SUP-MSFT-04",
                "name": "Microsoft Corporation",
                "status": "active",
                "country": "US",
                "currency": "USD",
                "risk_tier": "low",
                "payment_terms": "Net 30",
                "notes": "M365 Enterprise, Azure backup redundancy, and security licensing.",
            },
            {
                "code": "SUP-LNT-05",
                "name": "Larsen & Toubro Heavy Industrial",
                "status": "active",
                "country": "IN",
                "currency": "INR",
                "risk_tier": "medium",
                "payment_terms": "Net 60",
                "notes": "Turnkey engineering facilities, structural steel, and plant maintenance.",
            },
            {
                "code": "SUP-CSCO-06",
                "name": "Cisco Systems Inc",
                "status": "active",
                "country": "US",
                "currency": "USD",
                "risk_tier": "low",
                "payment_terms": "Net 45",
                "notes": "Enterprise core switches, edge SD-WAN hardware, and SmartNet.",
            },
            {
                "code": "SUP-RIL-07",
                "name": "Reliance Industrial Infrastructure",
                "status": "active",
                "country": "IN",
                "currency": "INR",
                "risk_tier": "low",
                "payment_terms": "Net 45",
                "notes": "High-bandwidth fiber trunk routes, dark fiber leases, power infra.",
            },
            {
                "code": "SUP-DLT-08",
                "name": "Deloitte Consulting LLP",
                "status": "active",
                "country": "US",
                "currency": "USD",
                "risk_tier": "medium",
                "payment_terms": "Net 30",
                "notes": "Global SOX compliance audit, supply chain optimization advisory.",
            },
        ]

        supplier_map = {}
        for s in suppliers_data:
            s_obj = Supplier(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                code=s["code"],
                name=s["name"],
                status=s["status"],
                country=s["country"],
                currency=s["currency"],
                risk_tier=s["risk_tier"],
                payment_terms=s["payment_terms"],
                notes=s["notes"],
                created_at=now - timedelta(days=120),
                updated_at=now,
                created_by=user_sub,
                updated_by=user_sub,
            )
            db.add(s_obj)
            supplier_map[s["code"]] = s_obj

        db.flush()

        contracts_data = [
            {
                "code": "CT-2026-TCS",
                "title": "IT Systems Integration & Offshore Engineering MSA",
                "supplier_code": "SUP-TCS-01",
                "status": "active",
                "contract_type": "Master Services Agreement",
                "currency": "INR",
                "value_minor": 1850000000, # 1.85 Cr INR
                "start_date": (now - timedelta(days=90)).date(),
                "end_date": (now + timedelta(days=275)).date(),
                "notes": "Critical vendor with Tier-1 99.95% SLA and Dedicated COE.",
            },
            {
                "code": "CT-2026-AWS",
                "title": "Global Cloud Infrastructure Enterprise Agreement",
                "supplier_code": "SUP-AWS-03",
                "status": "active",
                "contract_type": "Cloud Services Agreement",
                "currency": "USD",
                "value_minor": 240000000, # $2.4M
                "start_date": (now - timedelta(days=180)).date(),
                "end_date": (now + timedelta(days=185)).date(),
                "notes": "EDP discount commitment with multi-region failover guarantee.",
            },
            {
                "code": "CT-2026-LNT",
                "title": "Industrial Steel Fabrication & Facility Expansion FY26-27",
                "supplier_code": "SUP-LNT-05",
                "status": "pending_approval",
                "contract_type": "Procurement Contract",
                "currency": "INR",
                "value_minor": 420000000, # 4.2 Cr INR
                "start_date": (now - timedelta(days=10)).date(),
                "end_date": (now + timedelta(days=355)).date(),
                "notes": "Milestone-based stage payments tied to engineering signoffs.",
            },
            {
                "code": "CT-2026-MSFT",
                "title": "M365 E5 Security & Azure Cloud Enterprise Enrollment",
                "supplier_code": "SUP-MSFT-04",
                "status": "active",
                "contract_type": "Software Licensing",
                "currency": "USD",
                "value_minor": 85000000, # $850k
                "start_date": (now - timedelta(days=60)).date(),
                "end_date": (now + timedelta(days=305)).date(),
                "notes": "Unified support and 3,500 enterprise seats.",
            },
            {
                "code": "CT-2026-CSCO",
                "title": "Hardware Refresh & Campus SD-WAN Network Contract",
                "supplier_code": "SUP-CSCO-06",
                "status": "active",
                "contract_type": "Hardware & Support",
                "currency": "USD",
                "value_minor": 62000000, # $620k
                "start_date": (now - timedelta(days=30)).date(),
                "end_date": (now + timedelta(days=335)).date(),
                "notes": "Next-business-day on-site chassis replacement included.",
            },
        ]

        for c in contracts_data:
            s_obj = supplier_map[c["supplier_code"]]
            c_obj = Contract(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                code=c["code"],
                title=c["title"],
                supplier_id=s_obj.id,
                status=c["status"],
                contract_type=c["contract_type"],
                currency=c["currency"],
                value_minor=c["value_minor"],
                start_date=c["start_date"],
                end_date=c["end_date"],
                notes=c["notes"],
                created_at=now - timedelta(days=15),
                updated_at=now,
                created_by=user_sub,
                updated_by=user_sub,
            )
            db.add(c_obj)

        notifications_data = [
            {
                "kind": "contract_renewal",
                "title": "Contract Renewal Approaching (90 Days)",
                "body": "CT-2026-AWS Global Cloud Infrastructure renewal window is open. Evaluate discount commitment.",
                "link": "/contracts",
            },
            {
                "kind": "approval_required",
                "title": "Delegation of Authority Approval Pending",
                "body": "Contract CT-2026-LNT for Larsen & Toubro requires Director approval (exceeds $500,000 threshold).",
                "link": "/contracts",
            },
            {
                "kind": "supplier_tier",
                "title": "Annual Supplier Audit Completed",
                "body": "Tata Consultancy Services (TCS) audit finalized: Low Risk tier verified across all compliance pillars.",
                "link": "/suppliers",
            },
            {
                "kind": "spend_alert",
                "title": "Spend Anomaly Detected",
                "body": "Azure backup egress charges variance flagged (+8.4% vs monthly forecast).",
                "link": "/analytics",
            },
        ]

        for n in notifications_data:
            n_obj = Notification(
                id=str(uuid.uuid4()),
                tenant_id=tenant,
                user_sub="director",
                kind=n["kind"],
                title=n["title"],
                body=n["body"],
                link=n["link"],
                created_at=now - timedelta(hours=3),
                updated_at=now,
                created_by=user_sub,
                updated_by=user_sub,
            )
            db.add(n_obj)

        db.commit()
        print(f"Successfully seeded {len(suppliers_data)} suppliers, {len(contracts_data)} contracts, and {len(notifications_data)} notifications.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed()
