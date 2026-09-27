# Region Matrix

| Region | Locale | Currency | Timezone | Tax | Address | Language/RTL | Data residency | Feature flags |
|---|---|---|---|---|---|---|---|---|
| India | en-IN + configured | INR + configured | Asia/Kolkata | Configurable GST/tax profile | India | English + regional roadmap | Configurable | `region.in` |
| US | en-US | USD + configured | User/tenant | Configurable state/local | US | English | Configurable | `region.us` |
| EU | per member locale | EUR + local | Tenant/user | VAT profiles | Country-specific | Local/RTL where needed | Configurable | `region.eu` |
| GCC | en-* / ar-* | AED/SAR/QAR/etc | Country | Configurable | Country-specific | Arabic/English | Configurable | `region.gcc` |
| APAC | country-specific | country-specific | country-specific | Configurable | country-specific | country-specific | Configurable | `region.apac` |

This table is an implementation matrix, not a statement that all legal requirements are currently supported.
