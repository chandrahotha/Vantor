# Globalization

Country/regional rules must be configuration-driven.

Profiles:
RegionProfile, CurrencyProfile, TaxProfile, InvoiceProfile, CalendarProfile, AddressProfile, LanguageProfile, ProcurementPolicyProfile.

Support:
ISO country/currency codes, locale formatting, timezone-aware events, unit conversion, multiple languages, RTL UI, regional address formats, tax code catalogs, configurable invoice/e-document mappings, residency and retention policy.

Initial adapters:

India:
GST, GSTIN, e-invoicing/IRP concepts, IRN/QR references, tax components; applicability is effective-dated and source-driven.

Saudi Arabia:
VAT, Fatoora/e-invoicing Phase 1/Phase 2 concepts, Arabic/English, Saudi-specific e-invoice metadata; wave applicability is data/configuration.

EU:
VAT, cross-border flows, OSS/IOSS where relevant, e-invoicing and digital reporting; do not assume member-state domestic rules are identical.

Singapore:
GST, UEN, InvoiceNow/Peppol metadata and effective-dated rollout.

Australia/New Zealand:
GST, ABN/NZBN, tax invoice and Peppol e-invoicing metadata.

Brazil:
BRL and configurable NF-e/NFC-e/NFS-e fiscal-document mappings; do not collapse distinct document families.

Mexico:
MXN, RFC, CFDI metadata and electronic fiscal references.

No ruleset is legal advice. Every production rule must cite and periodically revalidate an authoritative source.
